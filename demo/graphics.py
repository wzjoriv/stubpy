# demo/graphics.py
# Concrete shape classes for the drawing library.
# Exercises: **kwargs MRO backtracing (4 levels), @dataclass, @classmethod
#            cls() detection, @property with type aliases, type-alias
#            preservation through Optional/Union, private variables, __all__.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Literal, Optional, Sequence

from demo import types
from demo.element import Element

__all__ = [
    "Shape",
    "Path",
    "Arc",
    "Rectangle",
    "Square",
    "Circle",
    "Text",
    "Gradient",
    "GradientStop",
]

# Private cache — should not appear in generated stubs by default.
_shape_registry: dict[str, type] = {}
_render_count:   int              = 0


# ---------------------------------------------------------------------------
# Gradient support (dataclass)
# ---------------------------------------------------------------------------

@dataclass
class GradientStop:
    """A single colour stop in a linear or radial gradient."""
    offset: float                  # 0.0–1.0
    color:  types.Color  = "black"
    opacity: float       = 1.0


@dataclass
class Gradient:
    """A linear or radial gradient definition.

    Exercises @dataclass with default_factory, ClassVar, and inherited fields
    when used as a base in future subclasses.
    """

    _registry_key: ClassVar[str] = "gradient"

    id:     str
    stops:  list[GradientStop]            = field(default_factory=list)
    angle:  float                         = 0.0
    units:  Literal["userSpace",
                    "objectBoundingBox"]  = "objectBoundingBox"

    def add_stop(self, offset: float, color: types.Color, opacity: float = 1.0) -> None:
        self.stops.append(GradientStop(offset, color, opacity))


# ---------------------------------------------------------------------------
# Base shape
# ---------------------------------------------------------------------------

class Shape(Element):
    """Adds stroke/fill styling on top of :class:`~demo.element.Element`.

    Exercises type-alias preservation: ``fill``, ``stroke``, etc. use
    ``types.Color`` / ``types.Length`` which must survive kwargs backtracing.
    """

    def __init__(
        self,
        fill:             types.Color                = "black",
        stroke:           types.Color | None         = None,
        stroke_width:     types.Length               = 1,
        stroke_linecap:   types.StrokeLineCap        = "butt",
        stroke_linejoin:  types.StrokeLineJoin       = "miter",
        stroke_dasharray: types.DashArray | None     = None,
        blend_mode:       types.BlendMode            = "normal",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.fill             = fill
        self.stroke           = stroke
        self.stroke_width     = stroke_width
        self.stroke_linecap   = stroke_linecap
        self.stroke_linejoin  = stroke_linejoin
        self.stroke_dasharray = stroke_dasharray
        self.blend_mode       = blend_mode

    # -- Abstract impl -------------------------------------------------------

    def render(self, compact: bool = False) -> str:
        return f"<shape fill='{self.fill}'/>"

    @property
    def bounding_box(self) -> types.BoundingBox:
        return (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

class Path(Shape):
    """SVG path — adds path data and optional event callbacks."""

    def __init__(
        self,
        d:          str                            = "",
        clip_path:  Optional[str]                  = None,
        on_click:   Callable[[], None] | None      = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.d         = d
        self.clip_path = clip_path
        self.on_click  = on_click

    # -- Builder methods -----------------------------------------------------

    def move_to(self, x: float, y: float) -> Path:
        self.d += f" M {x} {y}"
        return self

    def line_to(self, x: float, y: float) -> Path:
        self.d += f" L {x} {y}"
        return self

    def curve_to(
        self,
        cx1: float, cy1: float,
        cx2: float, cy2: float,
        x:   float, y:   float,
    ) -> Path:
        self.d += f" C {cx1} {cy1} {cx2} {cy2} {x} {y}"
        return self

    def close(self) -> Path:
        self.d += " Z"
        return self

    def render(self, compact: bool = False) -> str:
        return f"<path d='{self.d}'/>"

    @property
    def bounding_box(self) -> types.BoundingBox:
        return (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Arc  (4-level kwargs chain: Arc → Path → Shape → Element)
# ---------------------------------------------------------------------------

class Arc(Path):
    """Circular arc defined by sweep angle and angular offset.

    Tests four-level ``**kwargs`` backtracing through the full chain.
    """

    def __init__(
        self,
        angle:  float = 270.0,
        offset: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.angle  = angle
        self.offset = offset

    def __setitem__(self, attr: str, value: Any) -> None:
        if attr.lower() in ("angle", "offset"):
            setattr(self, attr.lower(), float(value) % 360)
        else:
            super().__setitem__(attr, value)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Rectangle  (2-level: Rectangle → Shape → Element)
# ---------------------------------------------------------------------------

class Rectangle(Shape):
    """Axis-aligned rectangle.  Tests two-level ``**kwargs`` backtracing."""

    def __init__(
        self,
        x:      types.Length = 0,
        y:      types.Length = 0,
        width:  types.Length = 100,
        height: types.Length = 100,
        rx:     types.Length = 0,
        ry:     types.Length = 0,
        **kwargs: Any,
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
        **kwargs: Any,
    ) -> Rectangle:
        """Construct from two corner points.

        Tests ``@classmethod`` with explicit params AND ``cls(**kwargs)``
        backtracing.
        """
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1, **kwargs)  # type: ignore[operator]

    def render(self, compact: bool = False) -> str:
        return f"<rect x='{self.x}' y='{self.y}' width='{self.width}' height='{self.height}'/>"

    @property
    def bounding_box(self) -> types.BoundingBox:
        return (float(self.x), float(self.y), float(self.width), float(self.height))  # type: ignore[arg-type]

    @property
    def area(self) -> float:
        return float(self.width) * float(self.height)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Square  (3-level: Square → Rectangle → Shape → Element)
# ---------------------------------------------------------------------------

class Square(Rectangle):
    """Square — own param is ``size``; all Rectangle/Shape/Element params via kwargs."""

    def __init__(self, size: types.Length = 100, **kwargs: Any) -> None:
        super().__init__(width=size, height=size, **kwargs)
        self.size = size


# ---------------------------------------------------------------------------
# Circle  (2-level; also tests @property returning type aliases and
#          @classmethod cls() backtracing)
# ---------------------------------------------------------------------------

class Circle(Shape):
    """Circle defined by centre (cx, cy) and radius r."""

    def __init__(
        self,
        cx: types.Length = 0,
        cy: types.Length = 0,
        r:  types.Length = 50,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.cx = cx
        self.cy = cy
        self.r  = r

    # -- Properties ----------------------------------------------------------

    @property
    def area(self) -> float:
        import math
        return math.pi * float(self.r) ** 2  # type: ignore[arg-type]

    @property
    def diameter(self) -> types.Length:
        return float(self.r) * 2  # type: ignore[return-value]

    @property
    def circumference(self) -> float:
        import math
        return 2 * math.pi * float(self.r)  # type: ignore[arg-type]

    # -- Factories -----------------------------------------------------------

    @classmethod
    def unit(cls, **kwargs: Any) -> Circle:
        """Unit circle (r=1) centred at origin."""
        return cls(r=1, cx=0, cy=0, **kwargs)

    @classmethod
    def at_origin(cls, r: types.Length = 50, **kwargs: Any) -> Circle:
        """Circle at (0, 0) with explicit radius."""
        return cls(r=r, cx=0, cy=0, **kwargs)

    # -- Rendering -----------------------------------------------------------

    def render(self, compact: bool = False) -> str:
        return f"<circle cx='{self.cx}' cy='{self.cy}' r='{self.r}'/>"

    @property
    def bounding_box(self) -> types.BoundingBox:
        r = float(self.r)  # type: ignore[arg-type]
        return (float(self.cx) - r, float(self.cy) - r, r * 2, r * 2)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

class Text(Shape):
    """Text element.  Exercises FontWeight and TextAnchor type aliases."""

    def __init__(
        self,
        content:     str                   = "",
        x:           types.Length          = 0,
        y:           types.Length          = 0,
        font_size:   types.Length          = 16,
        font_weight: types.FontWeight      = "normal",
        text_anchor: types.TextAnchor      = "start",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.content     = content
        self.x           = x
        self.y           = y
        self.font_size   = font_size
        self.font_weight = font_weight
        self.text_anchor = text_anchor

    def render(self, compact: bool = False) -> str:
        return f"<text x='{self.x}' y='{self.y}'>{self.content}</text>"

    @property
    def bounding_box(self) -> types.BoundingBox:
        return (float(self.x), float(self.y), 0.0, float(self.font_size))  # type: ignore[arg-type]
