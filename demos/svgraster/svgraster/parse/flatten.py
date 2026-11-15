"""Flattening of path segments (lines, Beziers, arcs) into polylines."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .pathdata import Path

DEFAULT_TOLERANCE = 0.1
MAX_SEGMENTS = 1000
CUBIC_WANG = 0.75
QUAD_WANG = 0.25
ARC_EPS = 1e-12


@dataclass
class Polyline:
    """A flattened subpath."""

    points: np.ndarray
    closed: bool = False

    def __len__(self) -> int:
        return len(self.points)

    @property
    def is_degenerate(self) -> bool:
        """Whether every point coincides."""
        return len(self.points) < 2 or bool(np.all(self.points == self.points[0]))


def _segments_for(dd: float, factor: float, tolerance: float) -> int:
    if dd <= 0:
        return 1
    return int(min(MAX_SEGMENTS, max(1, math.ceil(math.sqrt(factor * dd / tolerance)))))


def flatten_cubic(p0, p1, p2, p3, tolerance: float = DEFAULT_TOLERANCE) -> np.ndarray:
    """Points of a cubic Bezier excluding ``p0``."""
    p0, p1, p2, p3 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2, p3))
    dd = max(np.hypot(*(p0 - 2 * p1 + p2)), np.hypot(*(p1 - 2 * p2 + p3)))
    n = _segments_for(dd, CUBIC_WANG, tolerance)
    t = (np.arange(1, n + 1, dtype=np.float64) / n)[:, None]
    mt = 1.0 - t
    return mt ** 3 * p0 + 3 * mt * mt * t * p1 + 3 * mt * t * t * p2 + t ** 3 * p3


def flatten_quad(p0, p1, p2, tolerance: float = DEFAULT_TOLERANCE) -> np.ndarray:
    """Points of a quadratic Bezier excluding ``p0``."""
    p0, p1, p2 = (np.asarray(p, dtype=np.float64) for p in (p0, p1, p2))
    n = _segments_for(np.hypot(*(p0 - 2 * p1 + p2)), QUAD_WANG, tolerance)
    t = (np.arange(1, n + 1, dtype=np.float64) / n)[:, None]
    mt = 1.0 - t
    return mt * mt * p0 + 2 * mt * t * p1 + t * t * p2


def arc_center(x0, y0, rx, ry, rotation, large, sweep, x1, y1):
    """Endpoint to center parameterization: ``(cx, cy, rx, ry, phi, theta, dtheta)``."""
    phi = math.radians(rotation % 360.0)
    cos, sin = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cos * dx2 + sin * dy2
    y1p = -sin * dx2 + cos * dy2
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den > ARC_EPS else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos * cxp - sin * cyp + (x0 + x1) / 2.0
    cy = sin * cxp + cos * cyp + (y0 + y1) / 2.0
    theta = math.atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    end = math.atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx)
    dtheta = end - theta
    if sweep and dtheta < 0:
        dtheta += 2 * math.pi
    elif not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    return cx, cy, rx, ry, phi, theta, dtheta


def flatten_arc(x0, y0, rx, ry, rotation, large, sweep, x1, y1,
                tolerance: float = DEFAULT_TOLERANCE) -> np.ndarray:
    """Points of an elliptical arc excluding the start point."""
    if (x0 == x1 and y0 == y1):
        return np.empty((0, 2))
    if rx < ARC_EPS or ry < ARC_EPS:
        return np.array([[x1, y1]], dtype=np.float64)
    cx, cy, rx, ry, phi, theta, dtheta = arc_center(x0, y0, rx, ry, rotation, large, sweep, x1, y1)
    radius = max(rx, ry)
    step = 2.0 * math.acos(max(-1.0, 1.0 - tolerance / radius)) if tolerance < radius else math.pi / 2
    n = int(min(MAX_SEGMENTS, max(2, math.ceil(abs(dtheta) / max(step, ARC_EPS)))))
    angles = theta + dtheta * np.arange(1, n + 1, dtype=np.float64) / n
    ex, ey = rx * np.cos(angles), ry * np.sin(angles)
    cos, sin = math.cos(phi), math.sin(phi)
    pts = np.column_stack([cos * ex - sin * ey + cx, sin * ex + cos * ey + cy])
    pts[-1] = (x1, y1)
    return pts


def flatten_path(path: Path, tolerance: float = DEFAULT_TOLERANCE) -> list[Polyline]:
    """Flatten every subpath of ``path``."""
    result: list[Polyline] = []
    chunks: list[np.ndarray] = []
    cur = start = (0.0, 0.0)
    closed_last = False

    def finish(closed: bool) -> None:
        if len(chunks) > 1 or (chunks and closed):
            result.append(Polyline(np.concatenate(chunks), closed))
        chunks.clear()

    for seg in path.segments:
        kind = seg[0]
        if kind == "M":
            finish(False)
            cur = start = (seg[1], seg[2])
            chunks.append(np.array([cur], dtype=np.float64))
            closed_last = False
            continue
        if kind == "Z":
            if chunks:
                finish(True)
            cur = start
            closed_last = True
            continue
        if not chunks:
            chunks.append(np.array([cur], dtype=np.float64))
        if kind == "L":
            pts = np.array([[seg[1], seg[2]]], dtype=np.float64)
        elif kind == "C":
            pts = flatten_cubic(cur, seg[1:3], seg[3:5], seg[5:7], tolerance)
        elif kind == "Q":
            pts = flatten_quad(cur, seg[1:3], seg[3:5], tolerance)
        else:
            pts = flatten_arc(cur[0], cur[1], *seg[1:], tolerance=tolerance)
        if len(pts):
            chunks.append(pts)
            cur = (float(pts[-1, 0]), float(pts[-1, 1]))
        closed_last = False
    if not closed_last:
        finish(False)
    return result


def polylines_bbox(polylines: list[Polyline]) -> tuple[float, float, float, float] | None:
    """``(x0, y0, x1, y1)`` bounds of the polylines, or ``None`` when empty."""
    pts = [p.points for p in polylines if len(p.points)]
    if not pts:
        return None
    allp = np.concatenate(pts)
    return (float(allp[:, 0].min()), float(allp[:, 1].min()),
            float(allp[:, 0].max()), float(allp[:, 1].max()))
