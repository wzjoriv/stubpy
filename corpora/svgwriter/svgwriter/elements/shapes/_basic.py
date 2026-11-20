"""The ``Shape`` base class, ``rect``, ``circle`` and ``line``."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from ..._internal._typing import Self
from ...attributes.descriptors import Attr
from ...attributes.length import Length, LengthLike
from ...path.data import BBox, PathBuilder, PathData
from .._geometry import PathOperand
from .._mixins import GraphicsElement
from ..base import Category

__all__ = ["Circle", "Line", "Rect", "Shape", "user_units"]

KAPPA = 0.5522847498


def user_units(value: Any) -> float:
    """A length attribute in user units; unset counts as zero."""
    return 0.0 if value is None else Length.parse(value).to_user_units()


class Shape(PathOperand, GraphicsElement, ABC, category=Category.SHAPE):
    """Base class for the basic shapes and paths.

    Every shape converts to a ``<path>`` (:meth:`to_path`) and supports the
    geometric operators of :class:`~svgwriter.elements.PathOperand`.
    """

    @property
    @abstractmethod
    def bbox(self) -> BBox:
        """Geometric bounding box in user units, ignoring stroke and transform."""


class Rect(Shape, tag="rect"):
    """``<rect>`` with its top-left corner, size and optional corner radii."""

    geometry_attributes: ClassVar[frozenset[str]] = frozenset({"x", "y", "width", "height", "rx", "ry"})

    x = Attr[Length](convert=Length.parse)
    y = Attr[Length](convert=Length.parse)
    width = Attr[Length](convert=Length.parse)
    height = Attr[Length](convert=Length.parse)

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

    def local_outline(self) -> PathData:
        x, y, w, h = self.bbox
        return PathBuilder().move_to(x, y).line_to(x + w, y).line_to(x + w, y + h).line_to(x, y + h).close().build()


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
        cx, cy, r = user_units(self.cx), user_units(self.cy), user_units(self.r)
        k = r * KAPPA
        return (
            PathBuilder()
            .move_to(cx + r, cy)
            .curve_to(cx + r, cy + k, cx + k, cy + r, cx, cy + r)
            .curve_to(cx - k, cy + r, cx - r, cy + k, cx - r, cy)
            .curve_to(cx - r, cy - k, cx - k, cy - r, cx, cy - r)
            .curve_to(cx + k, cy - r, cx + r, cy - k, cx + r, cy)
            .close()
            .build()
        )


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
