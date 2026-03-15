# demo/graphics.py
# Full hierarchy: Element (element.py) → Shape → Path → Arc
#                                      → Rectangle → Square
#                                      → Circle (with @classmethod and @property)
# Exercises: **kwargs backtracing, type aliases, Literal, Callable, @classmethod
# cls() detection, @property, cross-module imports.
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence
from demo import types
from demo.element import Element

class Shape(Element):
    """Adds stroke/fill styling on top of Element."""

    def __init__(
        self,
        fill: types.Color = "black",
        stroke: types.Color | None = None,
        stroke_width: types.Length = 1,
        stroke_linecap: types.StrokeLineCap = "butt",
        stroke_linejoin: types.StrokeLineJoin = "miter",
        stroke_dasharray: types.DashArray | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.fill             = fill
        self.stroke           = stroke
        self.stroke_width     = stroke_width
        self.stroke_linecap   = stroke_linecap
        self.stroke_linejoin  = stroke_linejoin
        self.stroke_dasharray = stroke_dasharray


class Path(Shape):
    """Adds SVG path data and event callbacks on top of Shape."""

    def __init__(
        self,
        d: str = "",
        clip_path: Optional[str] = None,
        on_click: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.d         = d
        self.clip_path = clip_path
        self.on_click  = on_click

    def move_to(self, x: float, y: float) -> Path:
        self.d += f" M {x} {y}"
        return self

    def line_to(self, x: float, y: float) -> Path:
        self.d += f" L {x} {y}"
        return self

    def close(self) -> Path:
        self.d += " Z"
        return self


class Arc(Path):
    """
    Circular arc — own params are angle and offset.
    Everything else flows up through **kwargs:
      Arc → Path → Shape → Element
    Tests 4-level **kwargs backtracing.
    """

    def __init__(
        self,
        angle: float = 270,
        offset: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.angle  = angle
        self.offset = offset

    def __setitem__(self, attr: str, value: Any) -> None:
        attr = attr.lower()
        if attr in ("angle", "offset"):
            setattr(self, attr, value % 360)
        else:
            super().__setitem__(attr, value)


class Rectangle(Shape):
    """Axis-aligned rectangle — tests 2-level **kwargs (Rectangle → Shape → Element)."""

    def __init__(
        self,
        x: types.Length = 0,
        y: types.Length = 0,
        width: types.Length = 100,
        height: types.Length = 100,
        rx: types.Length = 0,
        ry: types.Length = 0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.x      = x
        self.y      = y
        self.width  = width
        self.height = height
        self.rx     = rx
        self.ry     = ry

    @classmethod
    def from_bounds(
        cls,
        x1: types.Length,
        x2: types.Length,
        y1: types.Length,
        y2: types.Length,
        **kwargs,
    ) -> Rectangle:
        """
        Construct from two corner points.
        Tests @classmethod with explicit params AND cls(**kwargs) backtracing.
        """
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1, **kwargs)


class Square(Rectangle):
    """
    Square — own param is `size`; all Rectangle/Shape/Element params via **kwargs.
    Tests 3-level chain through Rectangle.
    """

    def __init__(self, size: types.Length = 100, **kwargs) -> None:
        super().__init__(width=size, height=size, **kwargs)
        self.size = size


class Circle(Shape):
    """
    Circle defined by center (cx, cy) and radius r.
    Tests:
      - @property with return type
      - @classmethod with cls() backtracing (unit, at_origin)
    """

    def __init__(
        self,
        cx: types.Length = 0,
        cy: types.Length = 0,
        r: types.Length = 50,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.cx = cx
        self.cy = cy
        self.r  = r

    @property
    def area(self) -> float:
        import math
        return math.pi * float(self.r) ** 2  # type: ignore

    @property
    def diameter(self) -> types.Length:
        return float(self.r) * 2  # type: ignore

    @classmethod
    def unit(cls, **kwargs) -> Circle:
        """Unit circle (r=1) centred at origin. Tests cls(**kwargs) → __init__."""
        return cls(r=1, cx=0, cy=0, **kwargs)

    @classmethod
    def at_origin(cls, r: types.Length = 50, **kwargs) -> Circle:
        """Circle at (0,0) with explicit r. Tests cls() with mixed explicit + **kwargs."""
        return cls(r=r, cx=0, cy=0, **kwargs)