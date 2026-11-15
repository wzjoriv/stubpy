"""Exact measurement, hit testing and stroking of outlines."""

from __future__ import annotations

from typing import Any, Final, Literal

from ..path.data import BBox, PathData
from ..transform.matrix import Point
from ._skia import Geometry, from_skia, geometry_data, require_skia, to_skia

__all__ = [
    "Cap",
    "Join",
    "bounds",
    "contains",
    "point_at_length",
    "stroke_to_path",
    "tangent_at_length",
    "total_length",
]

Cap = Literal["butt", "round", "square"]
Join = Literal["miter", "round", "bevel"]

DEFAULT_STROKE_WIDTH: Final = 1.0
DEFAULT_MITER_LIMIT: Final = 4.0
MEASURE_PRECISION: Final = 16.0
_CAPS: Final = {"butt": "kButt_Cap", "round": "kRound_Cap", "square": "kSquare_Cap"}
_JOINS: Final = {"miter": "kMiter_Join", "round": "kRound_Join", "bevel": "kBevel_Join"}


def _skia_path(item: Geometry, feature: str) -> tuple[Any, Any]:
    skia = require_skia(feature)
    data, evenodd = geometry_data(item)
    return skia, to_skia(data, evenodd=evenodd)


def bounds(item: Geometry) -> BBox:
    """Tight bounding box computed from the curves, not from samples."""
    _, path = _skia_path(item, "exact bounds")
    rect = path.computeTightBounds()
    return BBox(rect.left(), rect.top(), rect.width(), rect.height())


def contains(item: Geometry, x: float, y: float) -> bool:
    """Whether ``(x, y)`` is inside the filled outline (honours ``fill-rule``)."""
    _, path = _skia_path(item, "hit testing")
    return bool(path.contains(x, y))


def _lengths(skia: Any, path: Any) -> list[float]:
    measure = skia.PathMeasure(path, False, MEASURE_PRECISION)
    lengths = []
    while True:
        lengths.append(measure.getLength())
        if not measure.nextContour():
            return lengths


def total_length(item: Geometry) -> float:
    """Length of every subpath added together, like ``getTotalLength()``."""
    skia, path = _skia_path(item, "path length")
    return sum(_lengths(skia, path))


def _position(item: Geometry, distance: float, feature: str) -> tuple[Point, Point]:
    skia, path = _skia_path(item, feature)
    lengths = _lengths(skia, path)
    if not any(lengths):
        raise ValueError("the outline has zero length")
    index, offset = len(lengths) - 1, lengths[-1]
    walked = 0.0
    for position, length in enumerate(lengths):
        if distance <= walked + length:
            index, offset = position, max(distance - walked, 0.0)
            break
        walked += length
    measure = skia.PathMeasure(path, False, MEASURE_PRECISION)
    for _ in range(index):
        measure.nextContour()
    point, tangent = measure.getPosTan(offset)
    return Point(point.x(), point.y()), Point(tangent.x(), tangent.y())


def point_at_length(item: Geometry, distance: float) -> Point:
    """Point *distance* along the outline, like ``getPointAtLength()``.

    Distances are clamped to ``0..total_length``.
    """
    return _position(item, distance, "point at length")[0]


def tangent_at_length(item: Geometry, distance: float) -> Point:
    """Unit tangent direction *distance* along the outline."""
    return _position(item, distance, "tangent at length")[1]


def stroke_to_path(
    item: Geometry,
    width: float = DEFAULT_STROKE_WIDTH,
    *,
    cap: Cap = "butt",
    join: Join = "miter",
    miter_limit: float = DEFAULT_MITER_LIMIT,
) -> PathData:
    """The filled outline a stroke of *width* would paint.

    Parameters
    ----------
    item : shape, text, PathData or str
        The outline to stroke.
    width : float
        Stroke width in user units.
    cap, join : str
        ``stroke-linecap`` and ``stroke-linejoin`` values.
    miter_limit : float
        ``stroke-miterlimit``.
    """
    skia, path = _skia_path(item, "stroke to path")
    paint = skia.Paint(
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=width,
        StrokeCap=getattr(skia.Paint, _CAPS[cap]),
        StrokeJoin=getattr(skia.Paint, _JOINS[join]),
        StrokeMiter=miter_limit,
    )
    result = skia.Path()
    paint.getFillPath(path, result)
    return from_skia(result)

