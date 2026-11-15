"""
tests/test_forwarding.py
------------------------
Comprehensive tests for **kwargs / *args forwarding chains across all
scenarios: method→function, function→method, method→method, function→class,
positional pre-binding, explicit keyword exclusion, if/else/for/try branch
union, nested function isolation, and *args / / / * param kinds.

These tests document and guard against regressions in the resolver's
positional-skip and self/cls-method-target features.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from tests.conftest import assert_valid_syntax

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub(src: str, **cfg_kwargs) -> str:
    """Generate stub for *src* text; validate syntax; return content."""
    src = textwrap.dedent(src)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(src)
        tmp = Path(f.name)
    try:
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(**cfg_kwargs)) if cfg_kwargs else StubContext()
        stub = generate_stub(str(tmp), str(tmp.with_suffix(".pyi")), ctx=ctx)
        assert_valid_syntax(stub)
        return stub
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_suffix(".pyi").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Positional pre-binding: f(bound_val, **kwargs)
# ---------------------------------------------------------------------------

class TestPositionalPreBinding:
    """When positional args fill the first N params of the target,
    those N params must NOT appear in the expanded stub."""

    def test_one_positional_arg_excluded(self):
        stub = _stub("""\
            def target(a: str, b: int = 1, c: float = 0.5) -> None: ...

            def caller(**kwargs) -> None:
                target("fixed", **kwargs)
        """)
        # 'a' is positionally bound to "fixed" — must not appear
        assert "b: int" in stub
        assert "c: float" in stub
        assert "a: str" not in stub.split("def caller")[1]

    def test_two_positional_args_excluded(self):
        stub = _stub("""\
            def configure(host: str, port: int, timeout: float = 30.0, retries: int = 3) -> None: ...

            def connect(server: str, **kwargs) -> None:
                configure(server, 8080, **kwargs)
        """)
        # host and port positionally bound (skip_n=2)
        connect_part = stub.split("def connect")[1]
        assert "timeout: float" in connect_part
        assert "retries: int" in connect_part
        assert "host: str" not in connect_part
        assert "port: int" not in connect_part

    def test_method_positional_arg_excluded(self):
        stub = _stub("""\
            def draw(element: str, width: int = 800, color: str = "black") -> None: ...

            class Canvas:
                def paint(self, **kwargs) -> None:
                    draw(self._elem, **kwargs)
        """)
        paint_part = stub.split("def paint")[1]
        assert "width: int" in paint_part
        assert "color: str" in paint_part
        assert "element: str" not in paint_part

    def test_zero_positional_args_all_included(self):
        """No positional pre-binding → all target params included."""
        stub = _stub("""\
            def target(a: str, b: int = 1) -> None: ...

            def caller(**kwargs) -> None:
                target(**kwargs)
        """)
        caller_part = stub.split("def caller")[1]
        assert "a: str" in caller_part
        assert "b: int" in caller_part


# ---------------------------------------------------------------------------
# Explicit keyword exclusion: f(key=val, **kwargs)
# ---------------------------------------------------------------------------

class TestExplicitKeywordExclusion:
    """Keyword args explicitly named in the call (key=val) are already
    satisfied and must NOT appear in the expanded stub."""

    def test_explicit_kwarg_excluded(self):
        stub = _stub("""\
            def render(color: str, opacity: float = 1.0, blend: str = "normal") -> str: ...

            class Shape:
                def draw(self, **kwargs) -> str:
                    return render(color=self._color, **kwargs)
        """)
        draw_part = stub.split("def draw")[1]
        assert "opacity: float" in draw_part
        assert "blend: str" in draw_part
        assert "color: str" not in draw_part

    def test_mixed_positional_and_explicit(self):
        """Both positional AND explicit kwargs are excluded."""
        stub = _stub("""\
            def f(a: str, b: int, c: float = 1.0, d: str = "x") -> None: ...

            def caller(**kwargs) -> None:
                f("fixed_a", b=42, **kwargs)
        """)
        caller_part = stub.split("def caller")[1]
        assert "c: float" in caller_part
        assert "d: str" in caller_part
        assert "a: str" not in caller_part
        assert "b: int" not in caller_part


# ---------------------------------------------------------------------------
# If/else branch union
# ---------------------------------------------------------------------------

class TestBranchUnion:
    """All branches contribute their params to the union.
    The stub contains ALL possible params, not just one branch."""

    def test_if_else_union_of_params(self):
        stub = _stub("""\
            def save_svg(*, width: int = 800, compress: bool = False) -> int: ...
            def save_png(*, width: int = 800, dpi: int = 96) -> int: ...

            def save(fmt: str = "svg", **kwargs) -> int:
                if fmt == "svg":
                    return save_svg(**kwargs)
                return save_png(**kwargs)
        """)
        # Split on "def save(" to get exactly the save() function stub
        save_part = stub.split("def save(")[1]
        assert "width: int" in save_part
        assert "compress: bool" in save_part   # from svg branch
        assert "dpi: int" in save_part          # from png branch

    def test_if_elif_else_union(self):
        stub = _stub("""\
            def fmt_a(x: int = 1) -> None: ...
            def fmt_b(y: str = "b") -> None: ...
            def fmt_c(z: float = 0.0) -> None: ...

            def process(fmt: str, **kwargs) -> None:
                if fmt == "a":
                    fmt_a(**kwargs)
                elif fmt == "b":
                    fmt_b(**kwargs)
                else:
                    fmt_c(**kwargs)
        """)
        proc_part = stub.split("def process")[1]
        assert "x: int" in proc_part
        assert "y: str" in proc_part
        assert "z: float" in proc_part

    def test_for_loop_union(self):
        """Targets inside for loops are also detected."""
        stub = _stub("""\
            def handler(action: str, payload: dict, retry: int = 3) -> None: ...

            def process_all(**kwargs) -> None:
                for item in items:
                    handler(item, {}, **kwargs)
        """)
        proc_part = stub.split("def process_all")[1]
        # handler has 2 positional args → skip_n=2, only retry remains
        assert "retry: int" in proc_part

    def test_try_except_union(self):
        """Targets in try and except blocks are both detected."""
        stub = _stub("""\
            def primary(x: int = 0, verbose: bool = False) -> None: ...
            def fallback(x: int = 0, silent: bool = True) -> None: ...

            def safe_call(**kwargs) -> None:
                try:
                    primary(**kwargs)
                except Exception:
                    fallback(**kwargs)
        """)
        safe_part = stub.split("def safe_call")[1]
        assert "x: int" in safe_part
        assert "verbose: bool" in safe_part
        assert "silent: bool" in safe_part

    @pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires 3.10+")
    def test_match_case_union(self):
        """Targets in match/case branches are detected (Python 3.10+)."""
        stub = _stub("""\
            def render_svg(*, width: int = 800) -> str: ...
            def render_png(*, dpi: int = 96) -> str: ...

            def render(fmt: str, **kwargs) -> str:
                match fmt:
                    case "svg": return render_svg(**kwargs)
                    case "png": return render_png(**kwargs)
                    case _: return ""
        """)
        rend_part = stub.split("def render(")[1]
        assert "width: int" in rend_part
        assert "dpi: int" in rend_part


# ---------------------------------------------------------------------------
# Nested function isolation
# ---------------------------------------------------------------------------

class TestNestedFunctionIsolation:
    """**kwargs forwarding inside nested functions must NOT be attributed
    to the outer function — each scope is independent."""

    def test_inner_function_not_leaked_to_outer(self):
        stub = _stub("""\
            def secret_target(secret_param: str) -> None: ...

            def outer(**kwargs) -> None:
                def inner():
                    secret_target(**kwargs)  # inner scope — NOT outer's forward
                inner()
        """)
        outer_part = stub.split("def outer")[1].split("def inner")[0]
        # outer's **kwargs should remain unresolved (or empty), not expanded
        # to secret_target's params since inner is a separate scope
        assert "secret_param: str" not in outer_part

    def test_class_inside_function_isolated(self):
        """Classes defined inside a function body don't leak to outer."""
        stub = _stub("""\
            def draw(color: str, size: int = 10) -> None: ...

            def factory(**kwargs):
                class Inner:
                    def go(self):
                        draw(**kwargs)  # inside nested class — not outer scope
                return Inner
        """)
        factory_part = stub.split("def factory")[1]
        # draw's params should NOT appear in factory's expanded stub
        assert "color: str" not in factory_part


# ---------------------------------------------------------------------------
# Method → method chains (self.X(**kwargs))
# ---------------------------------------------------------------------------

class TestMethodToMethodChain:
    """self.X(**kwargs) and cls.X(**kwargs) calls forward to sibling
    or parent methods — resolved via the class MRO."""

    def test_self_method_to_method(self):
        stub = _stub("""\
            class Renderer:
                def _render_svg(self, *, width: int = 800, compress: bool = False) -> str: ...
                def _render_png(self, *, width: int = 800, dpi: int = 96) -> str: ...

                def render(self, fmt: str = "svg", **kwargs) -> str:
                    if fmt == "svg":
                        return self._render_svg(**kwargs)
                    return self._render_png(**kwargs)
        """)
        render_part = stub.split("def render")[1]
        assert "width: int" in render_part
        assert "compress: bool" in render_part   # from svg branch
        assert "dpi: int" in render_part          # from png branch

    def test_self_method_positional_skip(self):
        """self.target(pos_val, **kwargs) should skip the first param."""
        stub = _stub("""\
            class Saver:
                def _write(self, path: str, data: bytes, *, encoding: str = "utf-8") -> None: ...

                def save(self, **kwargs) -> None:
                    self._write(self._path, self._data, **kwargs)
        """)
        save_part = stub.split("def save")[1]
        # path and data are positionally bound → skip_n=2
        assert "encoding: str" in save_part
        assert "path: str" not in save_part
        assert "data: bytes" not in save_part

    def test_method_to_method_deep_chain(self):
        """A → self.B(**kw) → self.C(**kw) chain resolves transitively."""
        stub = _stub("""\
            class Pipeline:
                def _compress(self, *, level: int = 6) -> bytes: ...

                def _encode(self, *, level: int = 6, checksum: bool = False) -> bytes:
                    return self._compress(level=level)

                def export(self, **kwargs) -> bytes:
                    return self._encode(**kwargs)
        """)
        export_part = stub.split("def export")[1]
        assert "level: int" in export_part

    def test_inherited_method_chain(self):
        """self.X(**kw) where X is inherited from a parent class."""
        stub = _stub("""\
            class Base:
                def _impl(self, *, speed: float = 1.0, verbose: bool = False) -> None: ...

            class Child(Base):
                def run(self, **kwargs) -> None:
                    self._impl(**kwargs)
        """)
        run_part = stub.split("def run")[1]
        assert "speed: float" in run_part
        assert "verbose: bool" in run_part


# ---------------------------------------------------------------------------
# Special parameter kinds: /, *, *args
# ---------------------------------------------------------------------------

class TestSpecialParamKinds:
    """Positional-only (PEP 570), keyword-only, and *args params are
    handled correctly through forwarding chains."""

    def test_keyword_only_params_preserved(self):
        stub = _stub("""\
            def setup(name: str, *, debug: bool = False, timeout: int = 30) -> None: ...

            def init(**kwargs) -> None:
                setup("app", **kwargs)
        """)
        init_part = stub.split("def init")[1]
        # name is positionally bound → excluded; kw-only params included
        assert "debug: bool" in init_part
        assert "timeout: int" in init_part
        assert "name: str" not in init_part

    def test_positional_only_promoted_on_absorption(self):
        """/ params absorbed via **kwargs become POSITIONAL_OR_KEYWORD."""
        stub = _stub("""\
            def low(x: float, y: float, /) -> float: ...

            def wrapper(**kwargs) -> float:
                return low(**kwargs)
        """)
        wrapper_part = stub.split("def wrapper")[1]
        assert "x: float" in wrapper_part
        assert "y: float" in wrapper_part
        # Promoted: no / separator in the wrapper stub
        assert "/" not in wrapper_part

    def test_args_forwarding_chain(self):
        stub = _stub("""\
            def process(*items: str, gamma: float = 1.0) -> list: ...

            def batch(*items: str, **opts) -> list:
                return process(*items, **opts)
        """)
        batch_part = stub.split("def batch")[1]
        assert "gamma: float" in batch_part

    def test_mixed_args_and_kwargs(self):
        stub = _stub("""\
            def render(*elements: str, width: int = 800, height: int = 600) -> str: ...

            def display(*args: str, **kwargs) -> str:
                return render(*args, **kwargs)
        """)
        display_part = stub.split("def display")[1]
        assert "width: int" in display_part
        assert "height: int" in display_part


# ---------------------------------------------------------------------------
# Cross-file chains
# ---------------------------------------------------------------------------

class TestCrossFileChains:
    def test_function_to_imported_function(self, tmp_path):
        (tmp_path / "base.py").write_text(
            "def configure(width: int = 800, height: int = 600, dpi: int = 96) -> None: pass\n"
        )
        (tmp_path / "app.py").write_text(
            "from base import configure\n\n"
            "def setup(**kwargs) -> None:\n"
            "    configure(**kwargs)\n"
        )
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            from stubpy import generate_stub
            from stubpy.context import StubContext
            stub = generate_stub(str(tmp_path / "app.py"),
                                 str(tmp_path / "app.pyi"), ctx=StubContext())
            assert "width: int" in stub
            assert "height: int" in stub
            assert "dpi: int" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_method_to_imported_function(self, tmp_path):
        (tmp_path / "lib.py").write_text(
            "def draw(x: float, y: float, color: str = 'black') -> None: pass\n"
        )
        (tmp_path / "canvas.py").write_text(
            "from lib import draw\n\n"
            "class Canvas:\n"
            "    def paint(self, **kwargs) -> None:\n"
            "        draw(**kwargs)\n"
        )
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            from stubpy import generate_stub
            from stubpy.context import StubContext
            stub = generate_stub(str(tmp_path / "canvas.py"),
                                 str(tmp_path / "canvas.pyi"), ctx=StubContext())
            paint = stub.split("def paint")[1]
            assert "x: float" in paint
            assert "y: float" in paint
            assert "color: str" in paint
        finally:
            sys.path.remove(str(tmp_path))

    def test_function_to_class_constructor(self, tmp_path):
        (tmp_path / "widgets.py").write_text(
            "class Button:\n"
            "    def __init__(self, label: str, width: int = 100) -> None: pass\n"
        )
        (tmp_path / "factory.py").write_text(
            "from widgets import Button\n\n"
            "def make_button(**kwargs) -> Button:\n"
            "    return Button(**kwargs)\n"
        )
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            from stubpy import generate_stub
            from stubpy.context import StubContext
            stub = generate_stub(str(tmp_path / "factory.py"),
                                 str(tmp_path / "factory.pyi"), ctx=StubContext())
            assert "label: str" in stub
            assert "width: int" in stub
        finally:
            sys.path.remove(str(tmp_path))


# ---------------------------------------------------------------------------
# Python version compatibility (guards for 3.10 and 3.14 regressions)
# ---------------------------------------------------------------------------

class TestVersionCompatibility:
    """Ensure annotation handling is robust across Python versions."""

    def test_builtin_list_subscript_direct(self):
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubContext
        ctx = StubContext()
        assert annotation_to_str(list[int], ctx) == "list[int]"

    def test_builtin_tuple_variadic_direct(self):
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubContext
        ctx = StubContext()
        assert annotation_to_str(tuple[int, ...], ctx) == "tuple[int, ...]"

    def test_builtin_dict_subscript_direct(self):
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubContext
        ctx = StubContext()
        assert annotation_to_str(dict[str, int], ctx) == "dict[str, int]"

    def test_nested_builtin_generics(self):
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubContext
        ctx = StubContext()
        assert annotation_to_str(list[tuple[int, str]], ctx) == "list[tuple[int, str]]"

    def test_union_legacy_mode_emits_Union_not_pipe(self):
        """In legacy mode, Union[str, int] must emit Union[str, int] not str | int."""
        import typing

        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        union_type = typing.Union[str, int]
        result = annotation_to_str(union_type, ctx)
        assert result == "Union[str, int]", f"Expected Union[str, int], got {result!r}"

    def test_union_legacy_optional_emits_Optional(self):
        """In legacy mode, Union[str, None] must emit Optional[str]."""
        import typing

        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        result = annotation_to_str(typing.Union[str, None], ctx)
        assert result == "Optional[str]", f"Got {result!r}"

    def test_pep604_union_legacy_mode(self):
        """str | int (runtime UnionType) in legacy mode emits Union[str, int]."""
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        result = annotation_to_str(str | int, ctx)
        assert result == "Union[str, int]", f"Got {result!r}"

    def test_pep604_union_modern_mode(self):
        """str | int in modern mode emits str | int."""
        from stubpy.annotations import annotation_to_str
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(union_style="modern"))
        result = annotation_to_str(str | int, ctx)
        assert result == "str | int", f"Got {result!r}"

    def test_dataclass_annotations_resolved_via_get_type_hints(self):
        """Dataclass field annotations are resolved via get_type_hints (3.14 compat)."""
        from dataclasses import dataclass

        from stubpy.context import StubContext
        from stubpy.emitter import generate_class_stub

        @dataclass
        class Point:
            x: float
            y: float = 0.0

        ctx = StubContext()
        stub = generate_class_stub(Point, ctx)
        assert "x: float" in stub
        assert "y: float" in stub
        # __init__ should have type annotations
        assert "def __init__" in stub
        init_part = stub.split("def __init__")[1]
        assert "x: float" in init_part

    def test_typeddict_fields_resolved_via_get_type_hints(self):
        """TypedDict fields are resolved via get_type_hints (3.14 compat)."""
        from typing import TypedDict

        from stubpy.context import StubContext
        from stubpy.emitter import generate_class_stub

        class Config(TypedDict):
            host: str
            port: int

        ctx = StubContext()
        stub = generate_class_stub(Config, ctx)
        assert "host: str" in stub
        assert "port: int" in stub
        assert "..." not in stub  # body must not be empty

    def test_get_type_hints_with_builtins_fallback(self):
        """get_type_hints succeeds even when __globals__ lacks builtins."""
        from stubpy.annotations import get_hints_for_method

        def fn() -> "list[int]": ...
        # Temporarily strip builtins from globals to simulate 3.10 edge case
        orig = fn.__globals__.get("__builtins__")
        fn.__globals__["__builtins__"] = {}
        try:
            result = get_hints_for_method(fn)
            # Should not raise; returns either resolved hints or fallback
            assert isinstance(result, dict)
        finally:
            if orig is None:
                fn.__globals__.pop("__builtins__", None)
            else:
                fn.__globals__["__builtins__"] = orig


# ---------------------------------------------------------------------------
# Demo package integration
# ---------------------------------------------------------------------------

class TestDemoDispatchStub:
    """End-to-end tests against demo/dispatch.py."""

    @pytest.fixture(scope="class")
    @classmethod
    def dispatch_stub(cls, tmp_path_factory):
        root = Path(__file__).resolve().parents[1]
        tmp = tmp_path_factory.mktemp("dispatch")
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()
        stub = generate_stub(
            str(root / "demo" / "dispatch.py"),
            str(tmp / "dispatch.pyi"),
            ctx=ctx,
        )
        return stub

    def test_syntax_valid(self, dispatch_stub):
        assert_valid_syntax(dispatch_stub)

    def test_property_mro_setter_present(self, dispatch_stub):
        """ColoredSVGRenderer overrides getter only — setter must come from MRO."""
        assert "class ColoredSVGRenderer" in dispatch_stub
        after = dispatch_stub.split("class ColoredSVGRenderer")[1]
        assert "@color.setter" in after.split("class ")[0]

    def test_cross_file_tint_expanded(self, dispatch_stub):
        """CrossFileRenderer.tint expands make_color params (r, g, b, a)."""
        after = dispatch_stub.split("class CrossFileRenderer")[1]
        tint = after.split("def tint")[1].split("def ")[0]
        assert "r: float" in tint
        assert "g: float" in tint
        assert "b: float" in tint
        assert "a: float" in tint

    def test_multiformat_renderer_union(self, dispatch_stub):
        """MultiFormatRenderer.render gets union of svg and png params."""
        assert "class MultiFormatRenderer" in dispatch_stub
        after = dispatch_stub.split("class MultiFormatRenderer")[1]
        render = after.split("def render")[1].split("def ")[0]
        assert "compress: bool" in render   # from svg branch
        assert "dpi: int" in render          # from png branch
        assert "width: int" in render        # shared

    def test_nested_isolation_no_save_svg_params(self, dispatch_stub):
        """IsolatedDispatcher.dispatch must NOT expand save_svg's params."""
        assert "class IsolatedDispatcher" in dispatch_stub
        after = dispatch_stub.split("class IsolatedDispatcher")[1]
        dispatch = after.split("def dispatch")[1].split("def ")[0]
        # save_svg params (width, height, compress) must not appear
        # since they're in the INNER function scope, not dispatch's scope
        assert "compress: bool" not in dispatch
        assert "dpi: int" not in dispatch


class TestIncrementalModeDemo:
    """Test incremental update with demo files."""

    def test_incremental_preserves_manual_content(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\ny: str = 'hello'\n")
        pyi = tmp_path / "mod.pyi"

        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext
        from stubpy.stub_merge import BEGIN_MARKER

        # First run: creates with markers
        ctx1 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx1)
        content1 = pyi.read_text()
        assert BEGIN_MARKER in content1

        # Add manual content outside markers
        pyi.write_text(f"# MyCustomClass = ...  # manual\n{content1}")

        # Second run: source changed
        src.write_text("z: float = 3.14\n")
        ctx2 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx2)
        content2 = pyi.read_text()
        assert "# MyCustomClass" in content2   # manual content preserved
        assert "z: float" in content2           # new content present
        assert_valid_syntax(content2)


# ---------------------------------------------------------------------------
# resolve_kwargs / resolve_args flags
# ---------------------------------------------------------------------------

class TestResolveKwargsFlag:
    """``resolve_kwargs=False`` / ``--no-resolve-kwargs`` keeps **kwargs as-is."""

    def test_kwargs_preserved_when_flag_false(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def __init__(self, color: str, size: float = 1.0) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(resolve_kwargs=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "**kwargs" in child_part
        assert "color" not in child_part
        assert "size" not in child_part

    def test_kwargs_expanded_by_default(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def __init__(self, color: str, size: float = 1.0) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.context import StubContext
        ctx = StubContext()  # resolve_kwargs=True by default
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "color: str" in child_part
        assert "size: float" in child_part

    def test_resolve_kwargs_false_in_toml(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text(
            "class A:\n"
            "    def f(self, x: int = 1) -> None: ...\n\n"
            "class B(A):\n"
            "    def f(self, **kwargs) -> None: ...\n"
        )
        (pkg / "stubpy.toml").write_text("resolve_kwargs = false\n")
        import sys
        sys.argv = ["stubpy", str(pkg), "-o", str(tmp_path / "stubs")]
        from stubpy.__main__ import main
        main()
        stub = (tmp_path / "stubs" / "mod.pyi").read_text()
        b_part = stub.split("class B")[1]
        assert "**kwargs" in b_part

    def test_cli_no_resolve_kwargs_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class A:\n"
            "    def f(self, x: int, y: str = 'a') -> None: ...\n\n"
            "class B(A):\n"
            "    def f(self, **kwargs) -> None: ...\n"
        )
        import sys
        sys.argv = ["stubpy", str(src), "--no-resolve-kwargs"]
        from stubpy.__main__ import main
        main()
        stub = src.with_suffix(".pyi").read_text()
        b_part = stub.split("class B")[1]
        assert "**kwargs" in b_part
        assert "x: int" not in b_part

    def test_resolve_args_false(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def process(*items: str, gamma: float = 1.0) -> list: ...\n\n"
            "def batch(*items: str, **opts) -> list:\n"
            "    return process(*items, **opts)\n"
        )
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(resolve_args=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        batch_part = stub.split("def batch")[1]
        assert "*items" in batch_part

    def test_typeshed_style_both_flags_false(self, tmp_path):
        """With both flags False, stub is plain **kwargs / *args (typeshed convention)."""
        src = tmp_path / "mod.py"
        src.write_text(
            "class Base:\n"
            "    def run(self, speed: float, *items: str, verbose: bool = False) -> None: ...\n\n"
            "class Child(Base):\n"
            "    def run(self, *args, **kwargs) -> None: ...\n"
        )
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext
        ctx = StubContext(config=StubConfig(resolve_kwargs=False, resolve_args=False))
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx)
        child_part = stub.split("class Child")[1]
        assert "*args" in child_part
        assert "**kwargs" in child_part
        assert "speed" not in child_part


# ---------------------------------------------------------------------------
# Type inference from default values
# ---------------------------------------------------------------------------

class TestTypeInferenceFromDefaults:
    """Unannotated parameters and variables with literal defaults get inferred types."""

    def test_function_params_inferred_from_defaults(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def f(x=0, y='hi', active=True, ratio=3.14, value=None): ...\n")
        from stubpy import generate_stub
        from stubpy.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub
        assert "ratio: float = 3.14" in stub
        assert "value: None = None" in stub

    def test_module_variable_types_inferred(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("MAX = 100\nLABEL = 'hi'\nFLAG = True\nRATE = 1.5\n")
        from stubpy import generate_stub
        from stubpy.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "MAX: int" in stub
        assert "LABEL: str" in stub
        assert "FLAG: bool" in stub
        assert "RATE: float" in stub

    def test_list_type_inferred_homogeneous(self, tmp_path):
        """AST-only mode infers list[int] from homogeneous list literals.
        Runtime mode only gets the bare `list` (from type(value).__name__)."""
        src = tmp_path / "mod.py"
        src.write_text("ITEMS = [1, 2, 3]\nSTRS = ['a', 'b']\n")
        from stubpy import generate_stub
        from stubpy.context import ExecutionMode, StubConfig, StubContext

        # AST-only: infers list[int], list[str] from literal elements
        ctx_ast = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
        stub_ast = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx_ast)
        assert "ITEMS: list[int]" in stub_ast
        assert "STRS: list[str]" in stub_ast

        # Runtime: gets bare list (type().__name__ doesn't inspect elements)
        ctx_rt = StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME))
        stub_rt = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=ctx_rt)
        assert "ITEMS: list" in stub_rt  # still better than nothing

    def test_ast_only_same_quality_as_runtime_for_literals(self, tmp_path):
        """AST-only mode should give same annotations as runtime for literal defaults."""
        src = tmp_path / "mod.py"
        src.write_text("def f(x=42, y='hello', z=True, w=1.0): ...\n")
        from stubpy import generate_stub
        from stubpy.context import ExecutionMode, StubConfig, StubContext
        stub_rt  = generate_stub(str(src), str(src.with_suffix(".pyi")),
                                 ctx=StubContext(config=StubConfig(execution_mode=ExecutionMode.RUNTIME)))
        stub_ast = generate_stub(str(src), str(src.with_suffix(".pyi")),
                                 ctx=StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY)))
        # Both should produce the same inferred type annotations
        assert "x: int = 42" in stub_rt
        assert "x: int = 42" in stub_ast
        assert "z: bool = True" in stub_rt
        assert "z: bool = True" in stub_ast

    def test_explicit_annotation_wins_over_inferred(self, tmp_path):
        """When both annotation and default exist, explicit annotation wins."""
        src = tmp_path / "mod.py"
        src.write_text("def f(x: float = 0, y: str = 'hello') -> None: ...\n")
        from stubpy import generate_stub
        from stubpy.context import StubContext
        stub = generate_stub(str(src), str(src.with_suffix(".pyi")), ctx=StubContext())
        assert "x: float = 0" in stub  # annotation says float, not int
        assert "y: str = 'hello'" in stub
        assert "# type:" not in stub
