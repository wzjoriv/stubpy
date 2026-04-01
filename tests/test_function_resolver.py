"""
tests/test_function_resolver.py
--------------------------------
Tests for module-level function **kwargs / *args backtracing via
:func:`stubpy.resolver.resolve_function_params` and the AST scanning
in :meth:`stubpy.ast_pass.ASTHarvester._harvest_function`.

Covers every parameter kind and edge case:
  - Simple **kwargs forwarding
  - Simple *args forwarding
  - Both *args and **kwargs forwarded to the same target
  - Chained / recursive forwarding (depth > 1)
  - Positional-only params (/) absorbed by **kwargs → promoted to POS_OR_KW
  - Keyword-only params (after *) inherited correctly
  - Default-ordering enforcement → non-default absorbed params become KEYWORD_ONLY
  - Typed *args preserved when still unresolved
  - Cycle detection (A→B→A)
  - Unknown target (name not in namespace) → variadics preserved
  - No-variadic function → no change
  - AST-only mode (no live_fn) → no crash
  - Async functions work through the emitter
  - Integration via generate_stub on demo/functions.py
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from typing import Any

import pytest

from stubpy.ast_pass import ast_harvest
from stubpy.context import StubContext, StubConfig
from stubpy.resolver import (
    _VAR_KW,
    _VAR_POS,
    _KW_ONLY,
    _POS_ONLY,
    _POS_KW,
    resolve_function_params,
    _enforce_signature_validity,
    _finalise_variadics,
    _merge_concrete_params,
    _normalise_kind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _param_names(result: list) -> list[str]:
    """Extract just parameter names from a ParamWithHints list."""
    out = []
    for p, _ in result:
        if p.kind == _VAR_POS:
            out.append(f"*{p.name}")
        elif p.kind == _VAR_KW:
            out.append(f"**{p.name}")
        else:
            out.append(p.name)
    return out


def _param_kinds(result: list) -> list[str]:
    """Extract parameter kind names."""
    kind_map = {
        inspect.Parameter.POSITIONAL_ONLY: "POS_ONLY",
        inspect.Parameter.POSITIONAL_OR_KEYWORD: "POS_KW",
        inspect.Parameter.VAR_POSITIONAL: "VAR_POS",
        inspect.Parameter.KEYWORD_ONLY: "KW_ONLY",
        inspect.Parameter.VAR_KEYWORD: "VAR_KW",
    }
    return [kind_map[p.kind] for p, _ in result]


def _compile_fn_from_source(src: str) -> tuple[Any, dict]:
    """Compile a source snippet and return (function, namespace)."""
    src = textwrap.dedent(src)
    ns: dict = {}
    exec(compile(src, "<test>", "exec"), ns)
    return ns


def _harvest_fn(src: str, name: str):
    """Return (live_fn, ast_info, namespace) for *name* from *src*."""
    ns = _compile_fn_from_source(src)
    syms = ast_harvest(textwrap.dedent(src))
    fi = next((f for f in syms.functions if f.name == name), None)
    return ns[name], fi, ns


def assert_valid_python(stub: str) -> None:
    """Assert that *stub* parses as valid Python."""
    try:
        ast.parse(stub)
    except SyntaxError as exc:
        raise AssertionError(f"Generated stub is not valid Python:\n{stub}") from exc


# ===========================================================================
# Unit tests: resolve_function_params
# ===========================================================================

class TestNoVariadics:
    def test_plain_function_unchanged(self):
        src = "def f(x: int, y: str = 'hi') -> None: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["x", "y"]

    def test_positional_only_preserved(self):
        src = "def f(a: int, b: int, /) -> int: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["a", "b"]
        assert all(p.kind == _POS_ONLY for p, _ in result)

    def test_keyword_only_preserved(self):
        src = "def f(*, x: int, y: str = 'hi') -> None: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["x", "y"]
        assert all(p.kind == _KW_ONLY for p, _ in result)

    def test_none_live_fn_returns_empty(self):
        result = resolve_function_params(None, None, {})
        assert result == []


class TestKwargsForwarding:
    def test_simple_forwarding_expands_params(self):
        src = """
        def target(r: float, g: float, b: float, a: float = 1.0): ...
        def wrapper(r: float = 1.0, **kwargs): target(r=r, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "r" in names
        assert "g" in names
        assert "b" in names
        assert "a" in names
        # **kwargs consumed
        assert "**kwargs" not in names

    def test_own_params_come_first(self):
        src = """
        def target(x: int, y: int): ...
        def wrapper(z: int, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert names[0] == "z", "own param must be first"

    def test_own_param_not_duplicated(self):
        src = """
        def target(r: float, g: float, b: float): ...
        def wrapper(r: float = 0.5, **kwargs): target(r=r, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert names.count("r") == 1

    def test_default_ordering_enforcement(self):
        """Non-default absorbed params following a default own-param → KEYWORD_ONLY."""
        src = """
        def target(x: int, y: int, z: int = 0): ...
        def wrapper(own: int = 5, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        # x and y have no defaults but follow own=5 → must be KW_ONLY
        kinds = {p.name: p.kind for p, _ in result}
        assert kinds["x"] == _KW_ONLY
        assert kinds["y"] == _KW_ONLY
        # z has a default — it may stay POS_KW or KW_ONLY depending on position
        # but the result must be valid Python
        stub = f"def wrapper({', '.join(_param_names(result))}): ..."
        # Verify by checking kinds directly rather than compile (names only)
        # The key invariant: no non-default follows a default in non-KW territory
        pos_params = [(p, h) for p, h in result if p.kind in (_POS_KW, _POS_ONLY)]
        seen_default = False
        for p, _ in pos_params:
            if p.default is not inspect.Parameter.empty:
                seen_default = True
            else:
                assert not seen_default, f"non-default {p.name!r} after default param"

    def test_residual_kwargs_when_target_still_open(self):
        """If the target also has **kwargs, our **kwargs is NOT consumed."""
        src = """
        def target(x: int, **kwargs): ...
        def wrapper(y: int, **kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "**kwargs" in names  # still open

    def test_no_ast_info_preserves_kwargs(self):
        """Without AST info, **kwargs is preserved unchanged."""
        src = "def target(x: int): ...\ndef wrapper(y: int, **kwargs): target(**kwargs)"
        ns = _compile_fn_from_source(src)
        # Deliberately pass ast_info=None
        result = resolve_function_params(ns["wrapper"], None, ns)
        names = _param_names(result)
        assert "**kwargs" in names

    def test_unknown_target_preserves_kwargs(self):
        """If the forwarding target is not in namespace, **kwargs is kept."""
        src = "def wrapper(x: int, **kwargs): unknown_func(**kwargs)"
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        assert "**kwargs" in _param_names(result)


class TestArgsForwarding:
    def test_typed_args_forwarded(self):
        """Typed *args from own function are preserved in output."""
        src = """
        def target(*items: str) -> None: ...
        def wrapper(*items: str, **kwargs) -> None: target(*items)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*items" in names

    def test_untyped_args_preserved_when_unresolved(self):
        """When *args target still has *args, we keep our *args."""
        src = """
        def target(*args, x: int = 1) -> None: ...
        def wrapper(*args, y: int = 2) -> None: target(*args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        assert "*args" in _param_names(result)

    def test_untyped_unresolved_args_not_in_output(self):
        """When *args fully resolved (target has no *args), it is dropped."""
        src = """
        def target(x: int, y: int) -> None: ...
        def wrapper(*args) -> None: target(*args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        # args is untyped and fully resolved → should not appear
        assert "*args" not in _param_names(result)

    def test_args_position_before_kwonly(self):
        """When *args is preserved, it appears before any keyword-only params.

        Note: ``def f(*items, verbose=False)`` is valid Python — after ``*items``
        all parameters are implicitly keyword-only, so the bare ``*`` is not
        needed (and would be a SyntaxError).
        """
        src = """
        def target(*items: str) -> None: ...
        def wrapper(*items: str, verbose: bool = False) -> None: target(*items)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*items" in names
        args_idx = names.index("*items")
        kw_idx = names.index("verbose")
        assert args_idx < kw_idx


class TestChainedForwarding:
    def test_two_level_chain(self):
        """A → B → C: resolve all the way down."""
        src = """
        def make_color(r: float, g: float, b: float, a: float = 1.0): ...
        def make_red(r: float = 1.0, **kwargs): make_color(r=r, **kwargs)
        def make_tinted(tint: float = 0.5, **kwargs): make_red(r=tint, **kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["make_tinted"]
        fi   = fi_by_name["make_tinted"]
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        names = _param_names(result)
        assert "g" in names
        assert "b" in names
        assert "a" in names
        assert "**kwargs" not in names

    def test_cycle_guard(self):
        """Mutually recursive forwarding (A→B→A) does not loop infinitely."""
        src = """
        def a(**kwargs): b(**kwargs)
        def b(**kwargs): a(**kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["a"]
        fi   = fi_by_name["a"]
        # Must complete without recursion error; **kwargs preserved as residual
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        assert "**kwargs" in _param_names(result)

    def test_three_level_chain_no_duplicate_params(self):
        """Deep chain should not produce duplicates."""
        src = """
        def base(x: int, y: int, z: int = 0): ...
        def mid(m: int, **kwargs): base(**kwargs)
        def top(t: int, **kwargs): mid(**kwargs)
        """
        ast_syms = ast_harvest(textwrap.dedent(src))
        ns = _compile_fn_from_source(src)
        fi_by_name = {f.name: f for f in ast_syms.functions}

        live = ns["top"]
        fi   = fi_by_name["top"]
        result = resolve_function_params(live, fi, ns, ast_info_by_name=fi_by_name)
        names = _param_names(result)
        assert len(names) == len(set(names)), "duplicate param names found"


class TestPositionalOnlyPromotion:
    def test_pos_only_absorbed_by_kwargs_becomes_pos_or_kw(self):
        """When a positional-only param is absorbed via **kwargs, it is promoted."""
        src = """
        def target(a: int, b: int, /) -> int: ...
        def wrapper(**kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        kinds = {p.name: p.kind for p, _ in result}
        # a and b are positional-only in target but absorbed via **kwargs
        # so they must become POSITIONAL_OR_KEYWORD in wrapper's stub
        assert kinds.get("a") == _POS_KW
        assert kinds.get("b") == _POS_KW


class TestMixedArgsAndKwargs:
    def test_both_forwarded(self):
        """Functions forwarding both *args and **kwargs simultaneously."""
        src = """
        def target(*colors: str, gamma: float = 1.0, r: float, g: float): ...
        def wrapper(*colors: str, **kwargs): target(*colors, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = _param_names(result)
        assert "*colors" in names  # typed *args preserved
        assert "gamma" in names
        assert "r" in names
        assert "g" in names


# ===========================================================================
# Unit tests: helper functions
# ===========================================================================

class TestNormaliseKind:
    def test_pos_only_promoted(self):
        p = inspect.Parameter("x", _POS_ONLY)
        assert _normalise_kind(p).kind == _POS_KW

    def test_pos_kw_unchanged(self):
        p = inspect.Parameter("x", _POS_KW)
        assert _normalise_kind(p).kind == _POS_KW

    def test_kw_only_unchanged(self):
        p = inspect.Parameter("x", _KW_ONLY)
        assert _normalise_kind(p).kind == _KW_ONLY

    def test_var_pos_unchanged(self):
        p = inspect.Parameter("args", _VAR_POS)
        assert _normalise_kind(p).kind == _VAR_POS

    def test_var_kw_unchanged(self):
        p = inspect.Parameter("kwargs", _VAR_KW)
        assert _normalise_kind(p).kind == _VAR_KW


class TestEnforceSignatureValidity:
    def test_no_defaults_unchanged(self):
        params = [
            (inspect.Parameter("x", _POS_KW), {}),
            (inspect.Parameter("y", _POS_KW), {}),
        ]
        result = _enforce_signature_validity(params)
        assert _param_kinds(result) == ["POS_KW", "POS_KW"]

    def test_non_default_after_default_promoted(self):
        p_with_default    = inspect.Parameter("a", _POS_KW, default=1)
        p_without_default = inspect.Parameter("b", _POS_KW)
        params = [(p_with_default, {}), (p_without_default, {})]
        result = _enforce_signature_validity(params)
        kinds = _param_kinds(result)
        assert kinds[0] == "POS_KW"   # a stays
        assert kinds[1] == "KW_ONLY"  # b promoted

    def test_already_kw_only_untouched(self):
        p_default    = inspect.Parameter("a", _POS_KW, default=1)
        p_kw_already = inspect.Parameter("b", _KW_ONLY)
        params = [(p_default, {}), (p_kw_already, {})]
        result = _enforce_signature_validity(params)
        assert _param_kinds(result)[1] == "KW_ONLY"

    def test_var_pos_skipped(self):
        p_default = inspect.Parameter("a", _POS_KW, default=1)
        p_varpos  = inspect.Parameter("args", _VAR_POS)
        p_after   = inspect.Parameter("b", _POS_KW)
        params = [(p_default, {}), (p_varpos, {}), (p_after, {})]
        result = _enforce_signature_validity(params)
        # VAR_POS skipped; b after it is POS_KW — position rule doesn't apply
        # (b comes before any defaulted positional param in the indexing that matters)
        # since first_default_idx=0 (p_default), p_varpos is at idx 1, and b is at idx 2
        # b has no default and idx 2 > 0, b.kind is POS_KW → promoted
        assert _param_kinds(result)[2] == "KW_ONLY"

    def test_empty_list(self):
        assert _enforce_signature_validity([]) == []


class TestMergeConcreteParams:
    def test_basic_merge(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("x", _POS_KW), {"x": int}),
            (inspect.Parameter("y", _POS_KW, default=1), {"y": int}),
        ]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 2
        assert seen == {"x", "y"}

    def test_deduplication(self):
        p_x = inspect.Parameter("x", _POS_KW)
        base = [(p_x, {})]
        seen = {"x"}
        source = [(inspect.Parameter("x", _POS_KW), {}),
                  (inspect.Parameter("y", _POS_KW), {})]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 2  # x not re-added, y added
        assert "y" in seen

    def test_variadics_skipped(self):
        base: list = []
        seen: set = set()
        source = [
            (inspect.Parameter("args", _VAR_POS), {}),
            (inspect.Parameter("kwargs", _VAR_KW), {}),
            (inspect.Parameter("x", _POS_KW), {}),
        ]
        _merge_concrete_params(base, seen, source)
        assert len(base) == 1
        assert base[0][0].name == "x"

    def test_pos_only_promoted(self):
        base: list = []
        seen: set = set()
        source = [(inspect.Parameter("a", _POS_ONLY), {})]
        _merge_concrete_params(base, seen, source)
        assert base[0][0].kind == _POS_KW


# ===========================================================================
# AST scanning tests
# ===========================================================================

class TestASTKwargsScanning:
    def test_kwargs_forwarded_to_populated(self):
        src = "def f(**kwargs): target(**kwargs)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.kwargs_forwarded_to

    def test_args_forwarded_to_populated(self):
        src = "def f(*args): target(*args)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.args_forwarded_to

    def test_no_forwarding_empty_lists(self):
        src = "def f(x: int, y: int): return x + y"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert fi.kwargs_forwarded_to == []
        assert fi.args_forwarded_to == []

    def test_multiple_targets_detected(self):
        src = """
        def f(**kwargs):
            a(**kwargs)
            b(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "a" in fi.kwargs_forwarded_to
        assert "b" in fi.kwargs_forwarded_to

    def test_non_forwarded_kwargs_call_not_detected(self):
        """Only **kwargs (the variadic) forwarding is detected, not literal dicts."""
        src = """
        def f(**kwargs):
            target(x=1, y=2)  # no **kwargs spread
        """
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" not in fi.kwargs_forwarded_to

    def test_method_body_also_scanned(self):
        """Methods inside classes also get kwargs_forwarded_to populated."""
        src = """
        class C:
            def method(self, **kwargs):
                helper(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        method_info = syms.classes[0].methods[0]
        assert "helper" in method_info.kwargs_forwarded_to

    def test_cls_call_detected_in_classmethod(self):
        """@classmethod that forwards to cls() is detected."""
        src = """
        class C:
            @classmethod
            def create(cls, **kwargs):
                return cls(**kwargs)
        """
        syms = ast_harvest(textwrap.dedent(src))
        method_info = syms.classes[0].methods[0]
        assert "cls" in method_info.kwargs_forwarded_to

    def test_async_function_scanned(self):
        src = "async def f(**kwargs): await target(**kwargs)"
        syms = ast_harvest(textwrap.dedent(src))
        fi = syms.functions[0]
        assert "target" in fi.kwargs_forwarded_to


# ===========================================================================
# Integration tests via generate_stub on demo/functions.py
# ===========================================================================

DEMO_DIR = Path(__file__).parent.parent / "demo"


class TestDemoFunctionsIntegration:
    """Run generate_stub on demo/functions.py and verify every stub."""

    @pytest.fixture(scope="class")
    def stub(self):
        from stubpy import generate_stub
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "functions.pyi")
            content = generate_stub(str(DEMO_DIR / "functions.py"), out)
        return content

    def test_syntax_valid(self, stub):
        assert_valid_python(stub)

    def test_make_color_correct(self, stub):
        """Base function unchanged."""
        assert "def make_color(" in stub
        assert "r: float" in stub
        assert "g: float" in stub
        assert "b: float" in stub
        assert "a: float = 1.0" in stub

    def test_make_color_red_kwargs_expanded(self, stub):
        """make_color_red(**kwargs) → expanded with g, b, a from make_color."""
        assert "def make_color_red(" in stub
        assert "**kwargs" not in stub.split("def make_color_red(")[1].split(")")[0]
        assert "g: float" in stub
        assert "b: float" in stub

    def test_make_color_red_default_ordering_valid(self, stub):
        """r=1.0 has default; absorbed g,b must be keyword-only (*) to stay valid."""
        section = stub.split("def make_color_red(")[1].split(") -> ")[0]
        # The * separator must appear before g and b
        star_idx = section.find("*,")
        g_idx = section.find("g: float")
        b_idx = section.find("b: float")
        assert star_idx != -1, "bare * separator missing"
        assert g_idx > star_idx
        assert b_idx > star_idx

    def test_make_color_blue_kwargs_expanded(self, stub):
        assert "def make_color_blue(" in stub
        assert "r: float" in stub

    def test_make_color_tinted_chained(self, stub):
        """make_color_tinted → make_color_red → make_color: depth-2 chain."""
        assert "def make_color_tinted(" in stub
        section = stub.split("def make_color_tinted(")[1].split(") -> ")[0]
        assert "tint" in section
        assert "g" in section
        assert "b" in section
        assert "**kwargs" not in section

    def test_normalise_range_pos_only(self, stub):
        """Positional-only params emit the / separator."""
        section = stub.split("def normalise_range(")[1].split(") -> ")[0]
        assert "/" in section

    def test_scaled_clamp_pos_only_and_kw_only(self, stub):
        """scaled_clamp has both / and * separators."""
        section = stub.split("def scaled_clamp(")[1].split(") -> ")[0]
        assert "/" in section
        assert "*" in section
        assert "scale" in section

    def test_stack_colors_typed_args(self, stub):
        """Typed *args preserved in stack_colors."""
        assert "*colors: types.Color" in stub

    def test_blend_colors_args_and_kwargs(self, stub):
        """blend_colors: *args typed + **kwargs expanded; no residual **kwargs."""
        section = stub.split("def blend_colors(")[1].split(") -> ")[0]
        assert "*colors" in section
        assert "**kwargs" not in section
        assert "gamma" in section

    def test_async_render_to_file(self, stub):
        assert "async def render_to_file(" in stub

    def test_no_private_functions_by_default(self, stub):
        assert "_resolve_color_string" not in stub
        assert "_bbox_union" not in stub

    def test_private_functions_with_flag(self):
        from stubpy import generate_stub
        import tempfile, os
        cfg = StubConfig(include_private=True)
        ctx = StubContext(config=cfg)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "functions.pyi")
            content = generate_stub(str(DEMO_DIR / "functions.py"), out, ctx=ctx)
        assert "_resolve_color_string" in content
        assert "_bbox_union" in content


class TestDemoPackageIntegration:
    """Run generate_stub on the entire demo package and sanity-check all stubs."""

    @pytest.fixture(scope="class")
    def stubs(self, tmp_path_factory):
        from stubpy.generator import generate_package
        out_dir = str(tmp_path_factory.mktemp("stubs"))
        result = generate_package(str(DEMO_DIR), output_dir=out_dir)
        files = {p.name: p.read_text() for p in result.stubs_written}
        return files

    def test_all_modules_generated(self, stubs):
        expected = {"functions.pyi", "container.pyi", "element.pyi",
                    "graphics.pyi", "mixed.pyi", "types.pyi", "variables.pyi"}
        assert expected.issubset(set(stubs.keys()))

    def test_all_stubs_valid_syntax(self, stubs):
        for name, content in stubs.items():
            assert_valid_python(content), f"{name} has invalid syntax"

    def test_functions_kwargs_expanded(self, stubs):
        funcs = stubs.get("functions.pyi", "")
        assert "def make_color_red(" in funcs
        assert "**kwargs" not in funcs.split("def make_color_red(")[1].split(")")[0]

    def test_container_kwargs_resolved(self, stubs):
        cont = stubs.get("container.pyi", "")
        # Container.__init__ has *elements, **kwargs → Element.__init__ params
        assert "def __init__(" in cont

    def test_zero_failures(self, stubs, tmp_path_factory):
        from stubpy.generator import generate_package
        out_dir = str(tmp_path_factory.mktemp("stubs2"))
        result = generate_package(str(DEMO_DIR), output_dir=out_dir)
        assert result.failed == [], f"Failed: {result.failed}"


# ===========================================================================
# CLI multi-file tests
# ===========================================================================

class TestCLIMultiFile:
    def test_two_files(self, tmp_path):
        """stubpy file1.py file2.py writes two stubs."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("def hello(name: str) -> str: ...")
        f2.write_text("def goodbye(name: str) -> None: ...")

        from stubpy.__main__ import main
        rc = main([str(f1), str(f2)])
        assert rc == 0
        assert (tmp_path / "a.pyi").exists()
        assert (tmp_path / "b.pyi").exists()

    def test_multi_file_output_flag_ignored_with_warning(self, tmp_path, capsys):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x: int = 1")
        f2.write_text("y: str = 'hi'")

        from stubpy.__main__ import main
        rc = main([str(f1), str(f2), "-o", str(tmp_path / "out")])
        assert rc == 0
        captured = capsys.readouterr()
        assert "ignored" in captured.err.lower()

    def test_single_file_mode_unchanged(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo(x: int) -> int: return x")
        from stubpy.__main__ import main
        rc = main([str(f)])
        assert rc == 0
        assert (tmp_path / "mod.pyi").exists()

    def test_mixed_file_and_dir(self, tmp_path):
        """Pass one file and one directory together."""
        # Create a sub-package
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("def helper(x: int) -> int: ...")

        solo = tmp_path / "solo.py"
        solo.write_text("CONST: str = 'hello'")

        from stubpy.__main__ import main
        rc = main([str(solo), str(pkg)])
        assert rc == 0
        assert (tmp_path / "solo.pyi").exists()
