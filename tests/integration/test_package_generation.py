"""End-to-end ``generate()`` over a whole multi-module package."""
from __future__ import annotations

import pytest

import stubpy
from tests.conftest import DRAWKIT, assert_valid_syntax, on_sys_path, write_tree

PIXELKIT: dict[str, str] = {
    **{
        path.replace("drawkit", "pixelkit"): text.replace("drawkit", "pixelkit")
        for path, text in DRAWKIT.items()
    },
    "pixelkit/primitives.py": """
        from __future__ import annotations

        import enum
        from abc import ABC, abstractmethod
        from typing import TypedDict


        class RenderOptions(TypedDict, total=False):
            compact: bool
            dpi: float


        class BlendMode(enum.Enum):
            NORMAL = "normal"
            MULTIPLY = "multiply"


        class Shape(ABC):
            def __init__(self, *, opacity: float = 1.0,
                         blend_mode: BlendMode = BlendMode.NORMAL) -> None:
                self.opacity = opacity

            @abstractmethod
            def area(self) -> float: ...


        class Circle(Shape):
            def __init__(self, cx: float, cy: float, radius: float, **kwargs) -> None:
                super().__init__(**kwargs)

            def area(self) -> float:
                return 0.0
    """,
    "pixelkit/style.py": """
        from typing import overload


        @overload
        def lerp(a: int, b: int, t: float) -> int: ...
        @overload
        def lerp(a: float, b: float, t: float) -> float: ...
        def lerp(a, b, t):
            return a + (b - a) * t
    """,
    "pixelkit/scene.py": """
        from typing import Generic, TypeVar

        T = TypeVar("T")


        class Stack(Generic[T]):
            def push(self, item: T) -> None: ...
            def pop(self) -> T: ...
    """,
    "pixelkit/export.py": """
        async def export_png(path: str, *, dpi: float = 96.0) -> int:
            return 0
    """,
    "pixelkit/variables.py": """
        from pixelkit import types

        __all__ = ["DEFAULT_FILL", "VERSION"]

        DEFAULT_FILL: types.Color = "black"
        VERSION = "1.0.0"
        _INTERNAL_DPI: int = 96
    """,
    "pixelkit/mixed.py": """
        from __future__ import annotations

        from pixelkit.container import Container

        __all__ = ["DEFAULT_COLOR", "Canvas"]

        DEFAULT_COLOR: str = "black"
        INTERNAL_CONSTANT: int = 42


        class Canvas(Container):
            def __init__(self, title: str = "Untitled", **kwargs) -> None:
                super().__init__(**kwargs)
    """,
}
"""The ``drawkit`` package renamed ``pixelkit``, plus modules of special class forms."""


@pytest.fixture(scope="module")
def pixelkit_stubs(tmp_path_factory):
    """Run ``generate()`` over ``pixelkit``; return ``({name: text}, result)``."""
    root = write_tree(tmp_path_factory.mktemp("pixelkit_root"), PIXELKIT)
    out = tmp_path_factory.mktemp("pixelkit_stubs")
    with on_sys_path(root, "pixelkit"):
        result = stubpy.generate(str(root / "pixelkit"), output=str(out))
    return {p.name: p.read_text(encoding="utf-8") for p in result.written}, result


@pytest.fixture(scope="module")
def stubs(pixelkit_stubs) -> dict[str, str]:
    """Generated stub text keyed by file name."""
    return pixelkit_stubs[0]


def _section(content: str, name: str) -> str:
    """Return the stub text of class *name* up to the next class."""
    return content.split(f"class {name}")[1].split("\nclass ")[0]


class TestPackageGeneration:
    def test_zero_failures(self, pixelkit_stubs):
        _, result = pixelkit_stubs
        assert result.failed == [], f"Failed: {result.failed}"

    def test_all_modules_generated(self, stubs):
        expected = {
            "primitives.pyi", "style.pyi", "scene.pyi", "export.pyi",
            "functions.pyi", "container.pyi", "element.pyi", "graphics.pyi",
            "dispatch.pyi", "mixed.pyi", "types.pyi", "variables.pyi",
        }
        assert expected.issubset(set(stubs))

    def test_all_stubs_valid_syntax(self, stubs):
        for name, content in stubs.items():
            try:
                assert_valid_syntax(content)
            except AssertionError as exc:
                raise AssertionError(f"{name}: {exc}") from exc

    def test_functions_kwargs_expanded(self, stubs):
        funcs = stubs["functions.pyi"]
        assert "def make_color_red(" in funcs
        assert "**kwargs" not in funcs.split("def make_color_red(")[1].split(")")[0]

    def test_container_kwargs_resolved(self, stubs):
        init = _section(stubs["container.pyi"], "Container").split("def __init__(")[1]
        init = init.split(") -> None")[0]
        assert "opacity: float" in init
        assert "**kwargs" not in init

    def test_mixed_subclass_kwargs_resolved_across_modules(self, stubs):
        canvas = _section(stubs["mixed.pyi"], "Canvas")
        assert "title: str = 'Untitled'" in canvas
        assert "clip: bool" in canvas
        assert "opacity: float" in canvas
        assert "**kwargs" not in canvas


class TestSpecialClassForms:
    def test_typeddict(self, stubs):
        assert "class RenderOptions(TypedDict, total=False):" in stubs["primitives.pyi"]

    def test_enum(self, stubs):
        content = stubs["primitives.pyi"]
        assert "class BlendMode(Enum):" in content
        assert "from enum import Enum" in content

    def test_abc(self, stubs):
        content = stubs["primitives.pyi"]
        assert "class Shape(ABC):" in content
        assert "@abstractmethod" in content

    def test_enum_default(self, stubs):
        """An enum member default renders as valid Python, not its repr."""
        content = stubs["primitives.pyi"]
        assert "BlendMode.NORMAL" in content
        assert "<BlendMode" not in content

    def test_kwargs_absorbed_through_abc_base(self, stubs):
        circle = _section(stubs["primitives.pyi"], "Circle")
        assert "blend_mode: BlendMode = BlendMode.NORMAL" in circle
        assert "opacity: float = 1.0" in circle
        assert "**kwargs" not in circle

    def test_overloads(self, stubs):
        assert stubs["style.pyi"].count("@overload") == 2

    def test_generics(self, stubs):
        content = stubs["scene.pyi"]
        assert "TypeVar" in content
        assert "Generic[T]" in content

    def test_async_function(self, stubs):
        assert "async def export_png" in stubs["export.pyi"]
