"""Basic shapes expressed as :class:`~svgraster.parse.pathdata.Path` objects."""
from __future__ import annotations

from collections.abc import Sequence

from .pathdata import Path


def rect_path(x: float, y: float, width: float, height: float, rx: float = 0.0, ry: float = 0.0) -> Path:
    """A rectangle, rounded when ``rx``/``ry`` are positive."""
    path = Path()
    if width <= 0 or height <= 0:
        return path
    rx, ry = min(rx, width / 2.0), min(ry, height / 2.0)
    if rx <= 0 or ry <= 0:
        return path.move_to(x, y).line_to(x + width, y).line_to(x + width, y + height).line_to(x, y + height).close()
    right, bottom = x + width, y + height
    path.move_to(x + rx, y).line_to(right - rx, y)
    path.arc_to(rx, ry, 0, False, True, right, y + ry).line_to(right, bottom - ry)
    path.arc_to(rx, ry, 0, False, True, right - rx, bottom).line_to(x + rx, bottom)
    path.arc_to(rx, ry, 0, False, True, x, bottom - ry).line_to(x, y + ry)
    path.arc_to(rx, ry, 0, False, True, x + rx, y)
    return path.close()


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> Path:
    """An ellipse starting at ``(cx + rx, cy)`` and sweeping clockwise on screen."""
    path = Path()
    if rx <= 0 or ry <= 0:
        return path
    path.move_to(cx + rx, cy)
    path.arc_to(rx, ry, 0, False, True, cx - rx, cy)
    path.arc_to(rx, ry, 0, False, True, cx + rx, cy)
    return path.close()


def circle_path(cx: float, cy: float, r: float) -> Path:
    """A circle."""
    return ellipse_path(cx, cy, r, r)


def line_path(x1: float, y1: float, x2: float, y2: float) -> Path:
    """A single line segment."""
    return Path().move_to(x1, y1).line_to(x2, y2)


def poly_path(coords: Sequence[float], closed: bool) -> Path:
    """A polyline or polygon from a flat coordinate list (odd trailing value dropped)."""
    path = Path()
    pairs = list(zip(coords[0::2], coords[1::2]))
    if len(pairs) < 2:
        return path
    path.move_to(*pairs[0])
    for x, y in pairs[1:]:
        path.line_to(x, y)
    return path.close() if closed else path
