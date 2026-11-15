"""Endpoint-to-center conversion for elliptical arcs (SVG 1.1, F.6.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from ..transform.matrix import Point

__all__ = ["CenterArc", "endpoint_to_center"]

FULL_TURN: Final = 2.0 * math.pi


@dataclass(frozen=True)
class CenterArc:
    """An arc in center parameterization.

    Angles are in radians; ``sweep`` is signed (positive is clockwise in
    SVG's y-down coordinate system).
    """

    cx: float
    cy: float
    rx: float
    ry: float
    rotation: float
    start_angle: float
    sweep: float

    def point_at(self, t: float) -> Point:
        """Point at parameter ``t`` in ``0..1`` along the arc."""
        angle = self.start_angle + self.sweep * t
        phi = math.radians(self.rotation)
        cos_phi, sin_phi = math.cos(phi), math.sin(phi)
        x = self.rx * math.cos(angle)
        y = self.ry * math.sin(angle)
        return Point(cos_phi * x - sin_phi * y + self.cx, sin_phi * x + cos_phi * y + self.cy)

    def sample(self, count: int) -> list[Point]:
        return [self.point_at(i / count) for i in range(count + 1)]


def _angle(ux: float, uy: float, vx: float, vy: float) -> float:
    dot = ux * vx + uy * vy
    length = math.hypot(ux, uy) * math.hypot(vx, vy)
    angle = math.acos(max(-1.0, min(1.0, dot / length)))
    return -angle if ux * vy - uy * vx < 0 else angle


def endpoint_to_center(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
) -> CenterArc | None:
    """Convert endpoint arc parameters to a ``CenterArc``.

    Returns ``None`` when the arc degenerates to a straight line (zero
    radius or coincident endpoints). Radii that are too small are scaled
    up as the specification requires.
    """
    if start == end or rx == 0 or ry == 0:
        return None
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (start.x - end.x) / 2.0, (start.y - end.y) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    scale = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if scale > 1.0:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)

    numerator = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, numerator / denominator))
    if large_arc == sweep:
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx

    cx = cos_phi * cxp - sin_phi * cyp + (start.x + end.x) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (start.y + end.y) / 2.0

    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    theta = _angle(1.0, 0.0, ux, uy)
    delta = _angle(ux, uy, vx, vy) % FULL_TURN
    if not sweep and delta > 0:
        delta -= FULL_TURN
    return CenterArc(cx, cy, rx, ry, rotation, theta, delta)
