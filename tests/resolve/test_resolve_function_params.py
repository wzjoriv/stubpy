"""Tests for resolve_function_params: function forwarding."""
from __future__ import annotations

import inspect
import textwrap

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY
from stubpy.analysis.harvest import ast_harvest
from stubpy.resolve import resolve_function_params
from tests.conftest import (
    _compile_fn_from_source,
    _harvest_fn,
    _param_names,
)


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
        assert all(p.kind == POS_ONLY for p, _ in result)

    def test_keyword_only_preserved(self):
        src = "def f(*, x: int, y: str = 'hi') -> None: ..."
        live, fi, ns = _harvest_fn(src, "f")
        result = resolve_function_params(live, fi, ns)
        assert _param_names(result) == ["x", "y"]
        assert all(p.kind == KW_ONLY for p, _ in result)

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
        kinds = {p.name: p.kind for p, _ in result}
        assert kinds["x"] == KW_ONLY
        assert kinds["y"] == KW_ONLY
        pos_params = [(p, h) for p, h in result if p.kind in (POS_KW, POS_ONLY)]
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
        assert "**kwargs" in names

    def test_no_ast_info_preserves_kwargs(self):
        """Without AST info, **kwargs is preserved unchanged."""
        src = "def target(x: int): ...\ndef wrapper(y: int, **kwargs): target(**kwargs)"
        ns = _compile_fn_from_source(src)
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
    def test_pos_only_not_absorbed_by_kwargs(self):
        """A positional-only param cannot be passed through **kwargs, so it is not absorbed."""
        src = """
        def target(a: int, b: int, /) -> int: ...
        def wrapper(**kwargs): target(**kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        names = [p.name for p, _ in result]
        assert "a" not in names and "b" not in names

    def test_pos_only_absorbed_by_args_stays_pos_only(self):
        """``*args`` forwarded positionally keeps the callee's positional-only parameters."""
        src = """
        def target(a: int, b: int, /) -> int: ...
        def wrapper(*args, **kwargs): target(*args, **kwargs)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        kinds = {p.name: p.kind for p, _ in result}
        assert kinds.get("a") == POS_ONLY
        assert kinds.get("b") == POS_ONLY

    def test_pos_only_after_own_params_becomes_pos_or_kw(self):
        """A positional-only param absorbed through *args after own params is promoted."""
        src = """
        def target(a: int, b: int, /) -> int: ...
        def wrapper(x, *args): target(x, *args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        result = resolve_function_params(live, fi, ns)
        assert [(p.name, p.kind) for p, _ in result] == [("x", POS_KW), ("b", POS_KW)]

    def test_args_only_call_drops_keyword_only(self):
        """Keyword-only callee parameters cannot be reached through ``*args`` alone."""
        src = """
        def target(a: int, *, d: int = 1) -> int: ...
        def wrapper(*args): target(*args)
        """
        live, fi, ns = _harvest_fn(src, "wrapper")
        assert [p.name for p, _ in resolve_function_params(live, fi, ns)] == ["a"]


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
        assert "*colors" in names
        assert "gamma" in names
        assert "r" in names
        assert "g" in names
