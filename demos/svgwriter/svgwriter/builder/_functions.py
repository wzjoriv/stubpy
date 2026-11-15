"""Functional constructors that forward keywords to element classes."""

from __future__ import annotations

from functools import partial
from typing import Any

from ..attributes.length import LengthLike
from ..color.color import Color
from ..document import Document
from ..elements.base import Child, Element
from ..elements.paint import LinearGradient, RadialGradient
from ..elements.shapes import Circle, Ellipse, Line, Path, Polygon, Polyline, Rect
from ..elements.structure import Group, Use
from ..elements.text import Text
from ..path.builder import PathBuilder
from ..path.data import PathDataLike

__all__ = [
    "circle",
    "document",
    "dot",
    "dashed_line",
    "ellipse",
    "group",
    "line",
    "linear_gradient",
    "outline",
    "path",
    "polygon",
    "polyline",
    "radial_gradient",
    "rect",
    "square",
    "text",
    "use",
]

DASH_PATTERN = (4, 2)
DOT_RADIUS = 2


def document(width: float, height: float, **kwargs: Any) -> Document:
    """A new :class:`Document`; keywords go to the root ``<svg>``."""
    return Document(width, height, **kwargs)


def rect(x: LengthLike, y: LengthLike, width: LengthLike, height: LengthLike, **kwargs: Any) -> Rect:
    return Rect(x, y, width, height, **kwargs)


def square(x: LengthLike, y: LengthLike, size: LengthLike, **kwargs: Any) -> Rect:
    return rect(x, y, size, size, **kwargs)


def circle(cx: LengthLike, cy: LengthLike, r: LengthLike, **kwargs: Any) -> Circle:
    return Circle(cx, cy, r, **kwargs)


def ellipse(cx: LengthLike, cy: LengthLike, rx: LengthLike, ry: LengthLike, **kwargs: Any) -> Ellipse:
    return Ellipse(cx, cy, rx, ry, **kwargs)


def line(x1: LengthLike, y1: LengthLike, x2: LengthLike, y2: LengthLike, **kwargs: Any) -> Line:
    return Line(x1, y1, x2, y2, **kwargs)


def polyline(*points: tuple[float, float], **kwargs: Any) -> Polyline:
    return Polyline(points, **kwargs)


def polygon(*points: tuple[float, float], **kwargs: Any) -> Polygon:
    return Polygon(points, **kwargs)


def path(d: PathDataLike | PathBuilder, **kwargs: Any) -> Path:
    return Path(d, **kwargs)


def text(content: str, x: LengthLike = 0, y: LengthLike = 0, **kwargs: Any) -> Text:
    return Text(content, x=x, y=y, **kwargs)


def group(*children: Child, **kwargs: Any) -> Group:
    return Group(*children, **kwargs)


def use(element: Element, x: LengthLike | None = None, y: LengthLike | None = None, **kwargs: Any) -> Use:
    return Use.of(element, x=x, y=y, **kwargs)


def linear_gradient(*colors: Color | str, vertical: bool = False, **kwargs: Any) -> LinearGradient:
    """Evenly spaced colors, left-to-right or top-to-bottom."""
    if vertical:
        return LinearGradient.vertical(*colors, **kwargs)
    return LinearGradient.horizontal(*colors, **kwargs)


def radial_gradient(*colors: Color | str, **kwargs: Any) -> RadialGradient:
    return RadialGradient.from_colors(colors, **kwargs)


outline = partial(rect, fill="none", stroke="black")
dashed_line = partial(line, stroke="black", stroke_dasharray=DASH_PATTERN)
dot = partial(circle, r=DOT_RADIUS)
