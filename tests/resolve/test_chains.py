"""Mixed method, function and class forwarding chains."""
from __future__ import annotations

from pathlib import Path

from stubpy.analysis.harvest import FunctionInfo
from stubpy.core.context import StubContext
from stubpy.core.pipeline import render_module
from stubpy.resolve import resolve_function_params, resolve_params


def _fi(name: str, kw_targets=(), pos_targets=()):
    """Build a minimal :class:`~stubpy.analysis.harvest.FunctionInfo` for tests."""
    return FunctionInfo(
        name=name,
        lineno=1,
        kwargs_forwarded_to=list(kw_targets),
        args_forwarded_to=list(pos_targets),
    )


class TestMethodToFunction:
    def test_method_kwargs_resolve_to_function_params(self, tmp_path):
        """A method that forwards **kwargs to a standalone function."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def draw(x: float, y: float, color: str = "black") -> None:
    pass

class Canvas:
    def paint(self, **kwargs) -> None:
        draw(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "x: float" in stub
        assert "y: float" in stub
        assert "color: str" in stub

    def test_method_to_function_deep_chain(self, tmp_path):
        """method → function → function chain."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def base(a: int, b: str = "x") -> None:
    pass

def middle(**kwargs) -> None:
    base(**kwargs)

class Obj:
    def entry(self, **kwargs) -> None:
        middle(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "a: int" in stub
        assert "b: str" in stub


class TestFunctionToClass:
    def test_function_kwargs_resolve_to_class_init(self, tmp_path):
        """A module-level function that forwards **kwargs to a class constructor."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Widget:
    def __init__(self, width: int = 100, height: int = 100, title: str = "") -> None:
        pass

def make_widget(**kwargs) -> Widget:
    return Widget(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "width: int" in stub
        assert "height: int" in stub
        assert "title: str" in stub


class TestMethodToMethod:
    def test_method_forwards_to_sibling_method(self, tmp_path):
        """Method A dispatches to method B on the same object via **kwargs."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Saver:
    def save_svg(self, path: str, *, width: int = 800, height: int = 600, compress: bool = False) -> int:
        return 0

    def save(self, path: str, **kwargs) -> int:
        return self.save_svg(path, **kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "width: int" in stub
        assert "height: int" in stub
        assert "compress: bool" in stub

    def test_method_dispatch_multiple_targets(self, tmp_path):
        """Method dispatches to different methods based on parameter — test union of params."""
        src = tmp_path / "mod.py"
        src.write_text('''\
class Renderer:
    def render_svg(self, *, width: int = 800, compress: bool = False) -> str:
        return ""

    def render_png(self, *, width: int = 800, dpi: int = 96) -> str:
        return ""

    def render(self, fmt: str = "svg", **kwargs) -> str:
        if fmt == "svg":
            return self.render_svg(**kwargs)
        return self.render_png(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "width: int" in stub


class TestCycleGuard:
    def test_recursive_forwarding_does_not_hang(self, tmp_path):
        """Mutually recursive forwarding must not cause infinite recursion."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def a(**kwargs):
    b(**kwargs)

def b(**kwargs):
    a(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "def a" in stub
        assert "def b" in stub

    def test_self_referential_method(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
class Tree:
    def visit(self, *, depth: int = 0, **kwargs) -> None:
        self.visit(depth=depth + 1, **kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "def visit" in stub


class TestMROWithNamespaceChain:
    def test_method_chain_mro_then_function(self, tmp_path):
        """Method inherits **kwargs via MRO, which then forward to a function."""
        src = tmp_path / "mod.py"
        src.write_text('''\
def low_level(speed: float = 1.0, power: float = 0.5) -> None:
    pass

class Base:
    def run(self, **kwargs) -> None:
        low_level(**kwargs)

class Child(Base):
    def run(self, label: str = "", **kwargs) -> None:
        super().run(**kwargs)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "label: str" in stub


class TestArgsForwardingFromFile:
    def test_star_args_forwarding(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text('''\
def process(*items: str, gamma: float = 1.0) -> list[str]:
    return list(items)

def batch(*items: str, **opts) -> list[str]:
    return process(*items, **opts)
''')
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "gamma: float" in stub


class TestResolveParamsWithNamespace:
    def test_method_resolves_via_namespace(self):
        def target_fn(x: int, y: str = "default") -> None:
            pass

        namespace = {"target_fn": target_fn}

        class MyClass:
            def method(self, **kwargs) -> None:
                target_fn(**kwargs)

        ast_info = _fi("method", kw_targets=["target_fn"])
        params = resolve_params(
            MyClass, "method",
            ast_info=ast_info,
            namespace=namespace,
        )
        names = [p.name for p, _ in params]
        assert "x" in names
        assert "y" in names

    def test_function_resolves_class_constructor(self):
        class Widget:
            def __init__(self, w: int, h: int = 100) -> None:
                pass

        def make(cls=Widget, **kwargs) -> "Widget":
            return cls(**kwargs)

        namespace = {"Widget": Widget}
        ast_info = _fi("make", kw_targets=["Widget"])

        params = resolve_function_params(make, ast_info, namespace)
        names = [p.name for p, _ in params]
        assert "w" in names
        assert "h" in names


class TestCrossFileChains:
    """Method in file A forwards **kwargs to function imported from file B."""

    def test_cross_file_method_to_function(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "lib.py").write_text(
                "def draw(x: float, y: float, color: str = 'black') -> None: pass\n"
            )
            (tmp_path / "canvas.py").write_text(
                "from lib import draw\n\n"
                "class Canvas:\n"
                "    def paint(self, **kwargs) -> None:\n"
                "        draw(**kwargs)\n"
            )
            from stubpy.core.context import StubContext
            ctx = StubContext()
            stub = render_module(str(tmp_path / "canvas.py"), ctx)
            assert "x: float" in stub
            assert "y: float" in stub
            assert "color: str" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_cross_file_function_to_function(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "base.py").write_text(
                "def configure(width: int = 800, height: int = 600, dpi: int = 96) -> None: pass\n"
            )
            (tmp_path / "app.py").write_text(
                "from base import configure\n\n"
                "def setup(**kwargs) -> None:\n"
                "    configure(**kwargs)\n"
            )
            from stubpy.core.context import StubContext
            ctx = StubContext()
            stub = render_module(str(tmp_path / "app.py"), ctx)
            assert "width: int" in stub
            assert "height: int" in stub
            assert "dpi: int" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_cross_file_function_to_class_init(self, tmp_path):
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            (tmp_path / "widgets.py").write_text(
                "class Button:\n"
                "    def __init__(self, label: str, width: int = 100) -> None: pass\n"
            )
            (tmp_path / "factory.py").write_text(
                "from widgets import Button\n\n"
                "def make_button(**kwargs) -> Button:\n"
                "    return Button(**kwargs)\n"
            )
            from stubpy.core.context import StubContext
            ctx = StubContext()
            stub = render_module(str(tmp_path / "factory.py"), ctx)
            assert "label: str" in stub
            assert "width: int" in stub
        finally:
            sys.path.remove(str(tmp_path))

    def test_demo_dispatch_cross_file_tint(self):
        """CrossFileRenderer.tint in demo/dispatch.py expands make_color params."""
        import sys
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root))
        try:
            from stubpy.core.context import StubContext
            ctx = StubContext()
            stub = render_module(str(root / "demo" / "dispatch.py"), ctx)
            assert "class CrossFileRenderer" in stub
            assert "r: float" in stub
            assert "g: float" in stub
            assert "b: float" in stub
        finally:
            pyi = root / "demo" / "dispatch.pyi"
            if pyi.exists():
                pyi.unlink()
            if str(root) in sys.path:
                sys.path.remove(str(root))
