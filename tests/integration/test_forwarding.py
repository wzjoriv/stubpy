"""End-to-end forwarding: call-site binding, branches and chains."""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from tests.conftest import assert_valid_syntax


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
        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext
        ctx = StubContext(config=StubConfig(**cfg_kwargs)) if cfg_kwargs else StubContext()
        stub = generate_stub(str(tmp), str(tmp.with_suffix(".pyi")), ctx=ctx)
        assert_valid_syntax(stub)
        return stub
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_suffix(".pyi").unlink(missing_ok=True)


class TestPositionalPreBinding:
    """When positional args fill the first N params of the target,
    those N params must NOT appear in the expanded stub."""

    def test_one_positional_arg_excluded(self):
        stub = _stub("""\
            def target(a: str, b: int = 1, c: float = 0.5) -> None: ...

            def caller(**kwargs) -> None:
                target("fixed", **kwargs)
        """)
        assert "b: int" in stub
        assert "c: float" in stub
        assert "a: str" not in stub.split("def caller")[1]

    def test_two_positional_args_excluded(self):
        stub = _stub("""\
            def configure(host: str, port: int, timeout: float = 30.0, retries: int = 3) -> None: ...

            def connect(server: str, **kwargs) -> None:
                configure(server, 8080, **kwargs)
        """)
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
        save_part = stub.split("def save(")[1]
        assert "width: int" in save_part
        assert "compress: bool" in save_part
        assert "dpi: int" in save_part

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
        assert "color: str" not in factory_part


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
        assert "compress: bool" in render_part
        assert "dpi: int" in render_part

    def test_self_method_positional_skip(self):
        """self.target(pos_val, **kwargs) should skip the first param."""
        stub = _stub("""\
            class Saver:
                def _write(self, path: str, data: bytes, *, encoding: str = "utf-8") -> None: ...

                def save(self, **kwargs) -> None:
                    self._write(self._path, self._data, **kwargs)
        """)
        save_part = stub.split("def save")[1]
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
            from stubpy.core.context import StubContext
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
            from stubpy.core.context import StubContext
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
            from stubpy.core.context import StubContext
            stub = generate_stub(str(tmp_path / "factory.py"),
                                 str(tmp_path / "factory.pyi"), ctx=StubContext())
            assert "label: str" in stub
            assert "width: int" in stub
        finally:
            sys.path.remove(str(tmp_path))
