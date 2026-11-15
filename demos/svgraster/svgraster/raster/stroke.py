"""Stroke outlining: dashes, joins and caps converted to fillable polygons.

Every emitted polygon is oriented with positive signed area, so filling them
together with the nonzero rule yields their union.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .. import _backend

JOINS = {"miter": 0, "round": 1, "bevel": 2}
CAPS = {"butt": 0, "round": 1, "square": 2}
MITER, ROUND, BEVEL = 0, 1, 2
BUTT, SQUARE = 0, 2
DEFAULT_TOLERANCE = 0.1
MIN_ROUND_SEGMENTS = 8
MAX_ROUND_SEGMENTS = 256
ROUND_JOIN_MIN_COS = math.cos(0.25)
COLLINEAR_EPS = 1e-12


def _orient(poly: np.ndarray) -> np.ndarray:
    x, y = poly[:, 0], poly[:, 1]
    area = np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)
    return poly[::-1].copy() if area < 0 else poly


def round_segments(radius: float, tolerance: float) -> int:
    """Segments for a circle of ``radius`` within ``tolerance``."""
    if radius <= tolerance:
        return MIN_ROUND_SEGMENTS
    step = 2.0 * math.acos(1.0 - tolerance / radius)
    return int(min(MAX_ROUND_SEGMENTS, max(MIN_ROUND_SEGMENTS, math.ceil(2.0 * math.pi / step))))


def circle_polygon(cx: float, cy: float, radius: float, tolerance: float = DEFAULT_TOLERANCE) -> np.ndarray:
    """A counter-clockwise polygon approximating a circle."""
    n = round_segments(radius, tolerance)
    ang = 2.0 * math.pi * np.arange(n, dtype=np.float64) / n
    return np.column_stack([cx + radius * np.cos(ang), cy + radius * np.sin(ang)])


def _dedupe(points: np.ndarray, closed: bool) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) == 0:
        return pts
    keep = np.ones(len(pts), dtype=bool)
    keep[1:] = np.any(pts[1:] != pts[:-1], axis=1)
    pts = pts[keep]
    if closed and len(pts) > 1 and np.all(pts[-1] == pts[0]):
        pts = pts[:-1]
    return pts


def _join(v, d0, d1, hw, join, miter_limit, tolerance, out) -> None:
    cross = d0[0] * d1[1] - d0[1] * d1[0]
    dot = d0[0] * d1[0] + d0[1] * d1[1]
    if abs(cross) <= COLLINEAR_EPS and dot > 0:
        return
    if join == ROUND and dot < ROUND_JOIN_MIN_COS:
        out.append(circle_polygon(v[0], v[1], hw, tolerance))
        return
    side = -1.0 if cross > 0 else 1.0
    n0 = np.array([-d0[1], d0[0]]) * side
    n1 = np.array([-d1[1], d1[0]]) * side
    a0, a1 = v + n0 * hw, v + n1 * hw
    if join == MITER and 1.0 + dot > COLLINEAR_EPS:
        ratio = 1.0 / math.sqrt((1.0 + dot) / 2.0)
        if ratio <= miter_limit:
            bis = n0 + n1
            tip = v + bis / math.hypot(bis[0], bis[1]) * hw * ratio
            out.append(_orient(np.array([v, a0, tip, a1])))
            return
    out.append(_orient(np.array([v, a0, a1])))


def _cap(p, d, hw, cap, tolerance, at_start, out) -> None:
    if cap == ROUND:
        out.append(circle_polygon(p[0], p[1], hw, tolerance))
    elif cap == SQUARE:
        nrm = np.array([-d[1], d[0]]) * hw
        ext = d * (-hw if at_start else hw)
        out.append(_orient(np.array([p + nrm, p - nrm, p - nrm + ext, p + nrm + ext])))


def py_stroke_polyline(points: np.ndarray, closed: bool, width: float, join: int = MITER, cap: int = BUTT,
                       miter_limit: float = 4.0, tolerance: float = DEFAULT_TOLERANCE) -> list[np.ndarray]:
    """Outline one polyline (numpy fallback)."""
    hw = width / 2.0
    pts = _dedupe(points, closed)
    out: list[np.ndarray] = []
    if hw <= 0 or len(pts) == 0:
        return out
    if len(pts) == 1:
        p = pts[0]
        if cap == ROUND:
            out.append(circle_polygon(p[0], p[1], hw, tolerance))
        elif cap == SQUARE:
            out.append(np.array([p + (-hw, -hw), p + (hw, -hw), p + (hw, hw), p + (-hw, hw)]))
        return out
    closed = closed and len(pts) > 2
    ends = np.roll(pts, -1, axis=0) if closed else pts[1:]
    starts = pts if closed else pts[:-1]
    vec = ends - starts
    dirs = vec / np.hypot(vec[:, 0], vec[:, 1])[:, None]
    for p0, p1, d in zip(starts, ends, dirs):
        nrm = np.array([-d[1], d[0]]) * hw
        out.append(_orient(np.array([p0 + nrm, p1 + nrm, p1 - nrm, p0 - nrm])))
    count = len(dirs)
    for i in range(1 if not closed else 0, count):
        _join(starts[i], dirs[i - 1], dirs[i], hw, join, miter_limit, tolerance, out)
    if not closed:
        _cap(pts[0], dirs[0], hw, cap, tolerance, True, out)
        _cap(pts[-1], dirs[-1], hw, cap, tolerance, False, out)
    return out


def normalize_dashes(dashes: Sequence[float]) -> list[float]:
    """The effective dash pattern, or ``[]`` when dashing is disabled."""
    values = [float(v) for v in dashes]
    if not values or any(v < 0 for v in values) or sum(values) <= 0:
        return []
    return values * 2 if len(values) % 2 else values


def py_dash_polyline(points: np.ndarray, closed: bool, dashes: Sequence[float],
                     offset: float = 0.0) -> list[np.ndarray]:
    """Split a polyline into dash polylines (numpy fallback)."""
    pattern = normalize_dashes(dashes)
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if not pattern:
        return [pts.copy()]
    if closed and len(pts) > 1:
        pts = np.vstack([pts, pts[:1]])
    total = sum(pattern)
    pos = offset % total
    idx = 0
    while pos >= pattern[idx]:
        pos -= pattern[idx]
        idx = (idx + 1) % len(pattern)
    rem = pattern[idx] - pos
    on = idx % 2 == 0
    out: list[np.ndarray] = []
    cur: list[np.ndarray] | None = [pts[0]] if on and len(pts) else None
    for a, b in zip(pts[:-1], pts[1:]):
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg_len == 0:
            continue
        t = 0.0
        while seg_len - t > rem:
            t += rem
            p = a + (b - a) * (t / seg_len)
            if on:
                cur.append(p)
                out.append(np.array(cur))
                cur = None
            else:
                cur = [p]
            idx = (idx + 1) % len(pattern)
            rem = pattern[idx]
            on = not on
        rem -= seg_len - t
        if on:
            cur.append(b)
    if on and cur:
        out.append(np.array(cur))
    return out


def stroke_polylines(polylines, width: float, join: str = "miter", cap: str = "butt",
                     miter_limit: float = 4.0, dashes: Sequence[float] = (), dash_offset: float = 0.0,
                     tolerance: float = DEFAULT_TOLERANCE) -> list[np.ndarray]:
    """Outline ``(points, closed)`` polylines into polygons, using nanobind when built."""
    native = _backend.native("composite")
    join_code, cap_code = JOINS[join], CAPS[cap]
    pattern = normalize_dashes(dashes)
    out: list[np.ndarray] = []
    for points, closed in polylines:
        pts = np.ascontiguousarray(points, dtype=np.float64).reshape(-1, 2)
        if native is not None:
            pieces = native.dash(pts, closed, pattern, dash_offset) if pattern else [(pts)]
            for piece in pieces:
                out.extend(native.stroke(np.ascontiguousarray(piece), closed and not pattern, width,
                                         join=join_code, cap=cap_code, miter_limit=miter_limit,
                                         tolerance=tolerance))
        else:
            pieces = py_dash_polyline(pts, closed, pattern, dash_offset) if pattern else [pts]
            for piece in pieces:
                out.extend(py_stroke_polyline(piece, closed and not pattern, width, join_code, cap_code,
                                              miter_limit, tolerance))
    return out
