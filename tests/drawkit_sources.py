"""Sources of ``drawkit``, a small multi-module package the integration tests stub (written to a temp dir)."""

DRAWKIT_TYPES = '''
    from typing import Literal, Sequence, Tuple, TypeAlias, Union

    Number: TypeAlias = int | float
    BoundingBox: TypeAlias = Tuple[float, float, float, float]
    Color: TypeAlias = Union[str, Tuple[float, float, float], Tuple[float, float, float, float]]
    Length: TypeAlias = Union[str, float, int]
    DashArray: TypeAlias = Union[str, Sequence[Number]]
    StrokeLineCap = Literal["butt", "round", "square"]
    StrokeLineJoin: TypeAlias = Literal["miter", "round", "bevel"]
'''

DRAWKIT_ELEMENT = '''
    from __future__ import annotations

    import abc
    from typing import Any, Dict, Optional

    from drawkit import types

    __all__ = ["Style", "Element"]


    class Style:
        def __init__(self, **props: Any) -> None:
            self._data: Dict[str, Any] = dict(props)

        def __setitem__(self, key: str, value: Any) -> None:
            self._data[key] = value

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> Style:
            return cls(**data)


    class Element(abc.ABC):
        def __init__(
            self,
            id: Optional[str] = None,
            title: Optional[str] = None,
            opacity: float = 1.0,
            visible: bool = True,
        ) -> None:
            self.id = id
            self.opacity = opacity

        @abc.abstractmethod
        def render(self, compact: bool = False) -> str: ...

        def translate(self, tx: float, ty: float = 0.0) -> Element:
            return self

        def rotate(self, angle: float, cx: Optional[float] = None, cy: Optional[float] = None) -> Element:
            return self

        def scale(self, sx: float, sy: Optional[float] = None) -> Element:
            return self

        @classmethod
        def blank(cls, **kwargs: Any) -> Element:
            return cls(opacity=0.0, **kwargs)
'''

DRAWKIT_CONTAINER = '''
    from __future__ import annotations

    from typing import Any, Callable, Iterator, Optional

    from drawkit.element import Element

    __all__ = ["Container", "Layer"]


    class Container(Element):
        def __init__(self, *elements: Element, clip: bool = False,
                     overflow: Optional[str] = None, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._children = list(elements)

        def add(self, *elements: Element) -> Container:
            return self

        def remove(self, element: Element) -> Container:
            return self

        def get(self, index: int) -> Element:
            return self._children[index]

        def clone(self, deep: bool = True) -> Container:
            return self

        def __iter__(self) -> Iterator[Element]:
            return iter(self._children)

        def __len__(self) -> int:
            return len(self._children)

        def render(self, compact: bool = False) -> str:
            return ""


    class Layer(Container):
        def __init__(
            self,
            name: str,
            z_index: int = 0,
            locked: bool = False,
            visible: bool = True,
            *,
            label: Optional[str] = None,
            on_change: Optional[Callable[[], None]] = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)

        def lock(self) -> Layer:
            return self

        def unlock(self) -> Layer:
            return self

        def hide(self) -> Layer:
            return self

        def show_layer(self) -> Layer:
            return self
'''

DRAWKIT_GRAPHICS = '''
    from __future__ import annotations

    from typing import Any, Callable, Optional

    from drawkit import types
    from drawkit.element import Element

    __all__ = ["Shape", "Path", "Arc", "Rectangle", "Square", "Circle"]


    class Shape(Element):
        def __init__(
            self,
            fill: types.Color = "black",
            stroke: types.Color | None = None,
            stroke_width: types.Length = 1,
            stroke_linecap: types.StrokeLineCap = "butt",
            stroke_linejoin: types.StrokeLineJoin = "miter",
            stroke_dasharray: types.DashArray | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)

        def render(self, compact: bool = False) -> str:
            return ""


    class Path(Shape):
        def __init__(self, d: str = "", clip_path: Optional[str] = None,
                     on_click: Callable[[], None] | None = None, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.d = d

        def move_to(self, x: float, y: float) -> Path:
            return self

        def line_to(self, x: float, y: float) -> Path:
            return self

        def close(self) -> Path:
            return self


    class Arc(Path):
        def __init__(self, angle: float = 270.0, offset: float = 0.0, **kwargs: Any) -> None:
            super().__init__(**kwargs)


    class Rectangle(Shape):
        def __init__(self, x: types.Length = 0, y: types.Length = 0,
                     width: types.Length = 100, height: types.Length = 100,
                     **kwargs: Any) -> None:
            super().__init__(**kwargs)

        @classmethod
        def from_bounds(cls, x1: types.Length, x2: types.Length, y1: types.Length,
                        y2: types.Length, **kwargs: Any) -> Rectangle:
            return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1, **kwargs)


    class Square(Rectangle):
        def __init__(self, size: types.Length = 100, **kwargs: Any) -> None:
            super().__init__(width=size, height=size, **kwargs)


    class Circle(Shape):
        def __init__(self, cx: types.Length = 0, cy: types.Length = 0,
                     r: types.Length = 50, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.r = r

        @property
        def area(self) -> float:
            return 3.14 * float(self.r) ** 2

        @property
        def diameter(self) -> types.Length:
            return float(self.r) * 2

        @classmethod
        def unit(cls, **kwargs: Any) -> Circle:
            return cls(r=1, cx=0, cy=0, **kwargs)

        @classmethod
        def at_origin(cls, r: types.Length = 50, **kwargs: Any) -> Circle:
            return cls(r=r, cx=0, cy=0, **kwargs)
'''

DRAWKIT_FUNCTIONS = '''
    from __future__ import annotations

    from drawkit import types

    __all__ = [
        "make_color", "make_color_red", "make_color_blue", "make_color_tinted",
        "normalise_range", "scaled_clamp", "stack_colors", "blend_colors",
        "render_to_file",
    ]


    def make_color(r: float, g: float, b: float, a: float = 1.0) -> types.Color:
        return (r, g, b, a)


    def make_color_red(r: float = 1.0, **kwargs) -> types.Color:
        return make_color(r=r, **kwargs)


    def make_color_blue(b: float = 1.0, **kwargs) -> types.Color:
        return make_color(b=b, **kwargs)


    def make_color_tinted(tint: float = 0.5, **kwargs) -> types.Color:
        return make_color_red(r=tint, **kwargs)


    def normalise_range(value: float, lo: float, hi: float, /) -> float:
        return (value - lo) / (hi - lo)


    def scaled_clamp(value: float, lo: float = 0.0, hi: float = 1.0, /, *, scale: float = 1.0) -> float:
        return max(lo, min(hi, value)) * scale


    def stack_colors(*colors: types.Color, gamma: float = 1.0) -> list[types.Color]:
        return list(colors)


    def blend_colors(*colors: types.Color, **kwargs) -> types.Color:
        stacked = stack_colors(*colors, **kwargs)
        if not stacked:
            return make_color(0.0, 0.0, 0.0)
        return make_color(0.0, 0.0, 0.0, **kwargs)


    async def render_to_file(path: str, *, compact: bool = False) -> int:
        return 0


    def _resolve_color_string(color: str) -> types.Color:
        return color


    def _bbox_union(*boxes: types.BoundingBox) -> types.BoundingBox:
        return boxes[0]
'''

DRAWKIT_DISPATCH = '''
    from __future__ import annotations

    from drawkit import types
    from drawkit.functions import make_color


    def save_svg(element: object, path: str, *, width: int = 800, height: int = 600,
                 compress: bool = False) -> int:
        return 0


    class ColoredMixin:
        @property
        def color(self) -> str:
            return "black"

        @color.setter
        def color(self, value: str) -> None:
            pass


    class ColoredSVGRenderer(ColoredMixin):
        @property
        def color(self) -> str:
            return super().color


    class CrossFileRenderer:
        def tint(self, **kwargs) -> types.Color:
            return make_color(**kwargs)


    class MultiFormatRenderer:
        def _render_svg(self, *, width: int = 800, height: int = 600, compress: bool = False) -> str:
            return ""

        def _render_png(self, *, width: int = 800, height: int = 600, dpi: int = 96) -> str:
            return ""

        def render(self, fmt: str = "svg", **kwargs) -> str:
            if fmt == "svg":
                return self._render_svg(**kwargs)
            return self._render_png(**kwargs)


    class IsolatedDispatcher:
        def dispatch(self, path: str, **kwargs) -> int:
            def _inner_save():
                return save_svg(object(), path, **kwargs)
            return _inner_save()
'''

DRAWKIT: dict[str, str] = {
    "drawkit/__init__.py": "",
    "drawkit/types.py": DRAWKIT_TYPES,
    "drawkit/element.py": DRAWKIT_ELEMENT,
    "drawkit/container.py": DRAWKIT_CONTAINER,
    "drawkit/graphics.py": DRAWKIT_GRAPHICS,
    "drawkit/functions.py": DRAWKIT_FUNCTIONS,
    "drawkit/dispatch.py": DRAWKIT_DISPATCH,
}
