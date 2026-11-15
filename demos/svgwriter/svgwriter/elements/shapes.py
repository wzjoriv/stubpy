"""Basic shapes and ``<path>``."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Final

from .._internal._typing import Points, Self
from ..attributes.descriptors import Attr
from ..attributes.length import Length, LengthLike
from ..path.builder import PathBuilder
from ..path.data import BBox, PathData, PathDataLike
from ._mixins import GraphicsElement
from .base import Category

__all__ = ["Circle", "Ellipse", "Line", "Path", "Polygon", "Polyline", "Rect", "Shape"]

_FULL_CIRCLE: Final = 360.0


def _user(value: Any) -> float:
    return 0.0 if value is None else Length.parse(value).to_user_units()


def _parse_points(text: str) -> list[tuple[float, float]]:
    numbers = [float(n) for n in text.replace(",", " ").split()]
    if len(numbers) % 2:
        raise ValueError("points need an even number of coordinates")
    return list(zip(numbers[::2], numbers[1::2]))


class Shape(GraphicsElement, ABC, category=Category.SHAPE):
    """Base class for the basic shapes and paths."""

    @property
    @abstractmethod
    def bbox(self) -> BBox:
        """Geometric bounding box in user units, ignoring stroke and transform."""


class Rect(Shape, tag="rect"):
    """``<rect>``.

    Parameters
    ----------
    x, y : length
        Top-left corner.
    width, height : length
        Size.
    rx, ry : length, optional
        Corner radii.
    **kwargs
        Presentation, core, conditional and other attributes.
    """

    x = Attr[Length](convert=Length.parse)
    y = Attr[Length](convert=Length.parse)
    width = Attr[Length](convert=Length.parse)
    height = Attr[Length](convert=Length.parse)
    rx = Attr[Length](convert=Length.parse)
    ry = Attr[Length](convert=Length.parse)

    def __init__(
        self,
        x: LengthLike = 0,
        y: LengthLike = 0,
        width: LengthLike = 0,
        height: LengthLike = 0,
        *,
        rx: LengthLike | None = None,
        ry: LengthLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(x=x, y=y, width=width, height=height, rx=rx, ry=ry)

    @classmethod
    def square(cls, size: LengthLike, **kwargs: Any) -> Self:
        return cls(width=size, height=size, **kwargs)

    @classmethod
    def from_bbox(cls, box: BBox, **kwargs: Any) -> Self:
        return cls(box.x, box.y, box.width, box.height, **kwargs)

    @property
    def bbox(self) -> BBox:
        return BBox(_user(self.x), _user(self.y), _user(self.width), _user(self.height))


class Circle(Shape, tag="circle"):
    """``<circle>``."""

    cx = Attr[Length](convert=Length.parse)
    cy = Attr[Length](convert=Length.parse)
    r = Attr[Length](convert=Length.parse)

    def __init__(self, cx: LengthLike = 0, cy: LengthLike = 0, r: LengthLike = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(cx=cx, cy=cy, r=r)

    @classmethod
    def from_bbox(cls, box: BBox, **kwargs: Any) -> Self:
        """Largest circle centered in *box*."""
        center = box.center
        return cls(center.x, center.y, min(box.width, box.height) / 2.0, **kwargs)

    @property
    def area(self) -> float:
        return math.pi * _user(self.r) ** 2

    @property
    def bbox(self) -> BBox:
        cx, cy, r = _user(self.cx), _user(self.cy), _user(self.r)
        return BBox(cx - r, cy - r, 2 * r, 2 * r)


class Ellipse(Shape, tag="ellipse"):
    """``<ellipse>``."""

    cx = Attr[Length](convert=Length.parse)
    cy = Attr[Length](convert=Length.parse)
    rx = Attr[Length](convert=Length.parse)
    ry = Attr[Length](convert=Length.parse)

    def __init__(
        self, cx: LengthLike = 0, cy: LengthLike = 0, rx: LengthLike = 0, ry: LengthLike = 0, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.update(cx=cx, cy=cy, rx=rx, ry=ry)

    @property
    def bbox(self) -> BBox:
        cx, cy, rx, ry = (_user(v) for v in (self.cx, self.cy, self.rx, self.ry))
        return BBox(cx - rx, cy - ry, 2 * rx, 2 * ry)


class Line(Shape, tag="line"):
    """``<line>``."""

    x1 = Attr[Length](convert=Length.parse)
    y1 = Attr[Length](convert=Length.parse)
    x2 = Attr[Length](convert=Length.parse)
    y2 = Attr[Length](convert=Length.parse)

    def __init__(
        self, x1: LengthLike = 0, y1: LengthLike = 0, x2: LengthLike = 0, y2: LengthLike = 0, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.update(x1=x1, y1=y1, x2=x2, y2=y2)

    @property
    def length(self) -> float:
        return math.hypot(_user(self.x2) - _user(self.x1), _user(self.y2) - _user(self.y1))

    @property
    def bbox(self) -> BBox:
        return BBox.from_points([(_user(self.x1), _user(self.y1)), (_user(self.x2), _user(self.y2))])


class Polyline(Shape, tag="polyline"):
    """``<polyline>``: an open sequence of straight segments."""

    def __init__(self, points: Points | str = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.points = points  # type: ignore[assignment]

    @property
    def points(self) -> list[tuple[float, float]]:
        raw = self.attributes.get("points", ())
        return _parse_points(raw) if isinstance(raw, str) else list(raw)

    @points.setter
    def points(self, value: Points | str) -> None:
        pairs = _parse_points(value) if isinstance(value, str) else [tuple(p) for p in value]
        self.attributes["points"] = tuple(pairs)

    @classmethod
    def regular(cls, cx: float, cy: float, radius: float, sides: int, **kwargs: Any) -> Self:
        """Vertices of a regular polygon, starting at the top."""
        step = _FULL_CIRCLE / sides
        pts = [
            (cx + radius * math.sin(math.radians(i * step)), cy - radius * math.cos(math.radians(i * step)))
            for i in range(sides)
        ]
        return cls(pts, **kwargs)

    @property
    def bbox(self) -> BBox:
        return BBox.from_points(self.points)


class Polygon(Polyline, tag="polygon"):
    """``<polygon>``: a closed ``Polyline``."""

    @property
    def area(self) -> float:
        """Signed-area magnitude (shoelace formula)."""
        pts = self.points
        total = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
        return abs(total) / 2.0


class Path(Shape, tag="path"):
    """``<path>``.

    Parameters
    ----------
    d : str, PathData, PathBuilder or iterable of commands
        The path data.
    path_length : float, optional
        Author's computed total length.
    **kwargs
        Presentation, core, conditional and other attributes.
    """

    path_length = Attr[float](convert=float)

    def __init__(self, d: PathDataLike | PathBuilder = "", *, path_length: float | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.d = d  # type: ignore[assignment]
        self.update(path_length=path_length)

    @property
    def d(self) -> PathData:
        raw = self.attributes.get("d", "")
        return raw if isinstance(raw, PathData) else PathData(raw)

    @d.setter
    def d(self, value: PathDataLike | PathBuilder) -> None:
        if isinstance(value, PathBuilder):
            value = value.build()
        self.attributes["d"] = value if isinstance(value, PathData) else PathData(value)

    @classmethod
    def build(cls, builder: PathBuilder, **kwargs: Any) -> Self:
        return cls(builder.build(), **kwargs)

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]], *, closed: bool = False, **kwargs: Any) -> Self:
        builder = PathBuilder()
        for i, (x, y) in enumerate(points):
            if i == 0:
                builder.move_to(x, y)
            else:
                builder.line_to(x, y)
        if closed:
            builder.close()
        return cls(builder, **kwargs)

    @property
    def bbox(self) -> BBox:
        return self.d.bbox or BBox(0.0, 0.0, 0.0, 0.0)
