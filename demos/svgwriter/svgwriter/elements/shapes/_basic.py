"""``rect``, ``circle``, ``ellipse`` and ``line``."""

from __future__ import annotations

import math
from typing import Any, ClassVar

from ..._internal._typing import Self
from ...attributes.descriptors import Attr
from ...attributes.length import Length, LengthLike
from ...path.builder import PathBuilder
from ...path.data import BBox, PathData
from ._base import Shape, user_units

__all__ = ["Circle", "Ellipse", "Line", "Rect"]


def _ellipse_outline(cx: float, cy: float, rx: float, ry: float) -> PathData:
    return (
        PathBuilder()
        .move_to(cx - rx, cy)
        .arc_to(rx, ry, 0, False, True, cx + rx, cy)
        .arc_to(rx, ry, 0, False, True, cx - rx, cy)
        .close()
        .build()
    )


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

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"x", "y", "width", "height", "rx", "ry"})
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
        return BBox(user_units(self.x), user_units(self.y), user_units(self.width), user_units(self.height))

    def corner_radii(self) -> tuple[float, float]:
        """Effective ``(rx, ry)`` after SVG's defaulting and clamping rules."""
        rx = None if self.rx is None else user_units(self.rx)
        ry = None if self.ry is None else user_units(self.ry)
        rx = ry if rx is None else rx
        ry = rx if ry is None else ry
        box = self.bbox
        return min(rx or 0.0, box.width / 2), min(ry or 0.0, box.height / 2)

    def local_outline(self) -> PathData:
        x, y, w, h = self.bbox
        rx, ry = self.corner_radii()
        builder = PathBuilder().move_to(x + rx, y).horizontal_to(x + w - rx)
        if rx and ry:
            builder.arc_to(rx, ry, 0, False, True, x + w, y + ry)
        builder.vertical_to(y + h - ry)
        if rx and ry:
            builder.arc_to(rx, ry, 0, False, True, x + w - rx, y + h)
        builder.horizontal_to(x + rx)
        if rx and ry:
            builder.arc_to(rx, ry, 0, False, True, x, y + h - ry)
        builder.vertical_to(y + ry)
        if rx and ry:
            builder.arc_to(rx, ry, 0, False, True, x + rx, y)
        return builder.close().build()


class Circle(Shape, tag="circle"):
    """``<circle>`` centered at ``(cx, cy)`` with radius ``r``."""

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"cx", "cy", "r"})
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
        return math.pi * user_units(self.r) ** 2

    @property
    def bbox(self) -> BBox:
        cx, cy, r = user_units(self.cx), user_units(self.cy), user_units(self.r)
        return BBox(cx - r, cy - r, 2 * r, 2 * r)

    def local_outline(self) -> PathData:
        r = user_units(self.r)
        return _ellipse_outline(user_units(self.cx), user_units(self.cy), r, r)


class Ellipse(Shape, tag="ellipse"):
    """``<ellipse>`` centered at ``(cx, cy)`` with radii ``rx`` and ``ry``."""

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"cx", "cy", "rx", "ry"})
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
        cx, cy, rx, ry = (user_units(v) for v in (self.cx, self.cy, self.rx, self.ry))
        return BBox(cx - rx, cy - ry, 2 * rx, 2 * ry)

    def local_outline(self) -> PathData:
        return _ellipse_outline(*(user_units(v) for v in (self.cx, self.cy, self.rx, self.ry)))


class Line(Shape, tag="line"):
    """``<line>`` from ``(x1, y1)`` to ``(x2, y2)``."""

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"x1", "y1", "x2", "y2"})
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
        return math.hypot(user_units(self.x2) - user_units(self.x1), user_units(self.y2) - user_units(self.y1))

    @property
    def bbox(self) -> BBox:
        return BBox.from_points([(user_units(self.x1), user_units(self.y1)), (user_units(self.x2), user_units(self.y2))])

    def local_outline(self) -> PathData:
        return PathBuilder().move_to(user_units(self.x1), user_units(self.y1)).line_to(user_units(self.x2), user_units(self.y2)).build()
