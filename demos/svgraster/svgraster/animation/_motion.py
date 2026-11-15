"""``animateMotion``: positions and orientation along a path, ``mpath`` and ``keyPoints``."""
from __future__ import annotations

import math

import numpy as np

from ..dom.units import parse_numbers
from ..parse.flatten import flatten_path
from ..parse.pathdata import Path, PathSyntaxError, parse_path
from ._values import bezier_ease, format_number, parse_key_times, parse_splines, segment_at

MOTION_TOLERANCE = 0.05


def _points_path(points: list[tuple[float, float]]) -> Path:
    path = Path()
    for i, (x, y) in enumerate(points):
        (path.move_to if i == 0 else path.line_to)(x, y)
    return path


def _point_list(text: str | None) -> list[tuple[float, float]]:
    out = []
    for chunk in (text or "").split(";"):
        nums = parse_numbers(chunk)
        if len(nums) >= 2:
            out.append((nums[0], nums[1]))
    return out


def motion_path(anim, document) -> tuple[Path, list[tuple[float, float]]]:
    """The motion path and its vertex list (for ``values``/``from``/``to``/``by``)."""
    mpath = next((c for c in anim.children if c.tag == "mpath"), None)
    if mpath is not None and document is not None:
        ref = document.lookup(mpath.href, "path")
        if ref is not None:
            try:
                return parse_path(ref.get("d", "")), []
            except PathSyntaxError:
                return Path(), []
    if anim.get("path"):
        try:
            return parse_path(anim.get("path")), []
        except PathSyntaxError:
            return Path(), []
    points = _point_list(anim.get("values"))
    if not points:
        start = _point_list(anim.get("from"))
        end = _point_list(anim.get("to"))
        by = _point_list(anim.get("by"))
        origin = start[0] if start else (0.0, 0.0)
        if end:
            points = [origin, end[0]]
        elif by:
            points = [origin, (origin[0] + by[0][0], origin[1] + by[0][1])]
    return _points_path(points), points


class MotionPath:
    """Arc-length sampling of a flattened motion path."""

    def __init__(self, path: Path):
        lines = flatten_path(path, MOTION_TOLERANCE)
        pts = [p.points for p in lines if len(p.points)]
        self.points = np.concatenate(pts) if pts else np.zeros((0, 2))
        seg = np.hypot(*np.diff(self.points, axis=0).T) if len(self.points) > 1 else np.zeros(0)
        self.cumulative = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.cumulative[-1])

    def at(self, fraction: float) -> tuple[float, float, float]:
        """``(x, y, tangent angle in degrees)`` at a fraction of the length."""
        if len(self.points) == 0:
            return 0.0, 0.0, 0.0
        if len(self.points) == 1 or self.length <= 0:
            return float(self.points[0, 0]), float(self.points[0, 1]), 0.0
        d = min(max(fraction, 0.0), 1.0) * self.length
        i = int(np.searchsorted(self.cumulative, d, side="right")) - 1
        i = min(max(i, 0), len(self.points) - 2)
        while i > 0 and self.cumulative[i + 1] - self.cumulative[i] <= 0:
            i -= 1
        span = self.cumulative[i + 1] - self.cumulative[i]
        t = (d - self.cumulative[i]) / span if span > 0 else 0.0
        p0, p1 = self.points[i], self.points[i + 1]
        x, y = p0 + (p1 - p0) * t
        return float(x), float(y), math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))


def motion_transform(anim, document, p: float) -> str:
    """The supplemental transform for progress ``p`` of the simple duration."""
    path, vertices = motion_path(anim, document)
    measure = MotionPath(path)
    mode = anim.get("calcMode", "paced")
    key_times = parse_key_times(anim.get("keyTimes"))
    key_points = parse_key_times(anim.get("keyPoints"))
    if key_points and len(key_points) == len(key_times) and len(key_points) > 1:
        if mode == "discrete":
            idx = max(0, int(np.searchsorted(key_times, p, side="right")) - 1)
            fraction = key_points[min(idx, len(key_points) - 1)]
        else:
            i, local = segment_at(key_times, p)
            splines = parse_splines(anim.get("keySplines"))
            if mode == "spline" and i < len(splines):
                local = bezier_ease(splines[i], local)
            fraction = key_points[i] + (key_points[i + 1] - key_points[i]) * local
    elif vertices and mode in ("linear", "discrete", "spline") and len(vertices) > 1:
        n = len(vertices)
        cum = measure.cumulative
        stops = [0.0]
        for k in range(1, n):
            stops.append(float(np.hypot(vertices[k][0] - vertices[k - 1][0], vertices[k][1] - vertices[k - 1][1])))
        offsets = np.cumsum(stops) / (cum[-1] if cum[-1] > 0 else 1.0)
        times = key_times if len(key_times) == n else [k / (n - 1) for k in range(n)]
        if mode == "discrete":
            idx = max(0, int(np.searchsorted(times, p, side="right")) - 1)
            fraction = float(offsets[min(idx, n - 1)])
        else:
            i, local = segment_at(times, min(p, 1.0))
            fraction = float(offsets[i] + (offsets[i + 1] - offsets[i]) * local)
    else:
        fraction = p
    x, y, angle = measure.at(fraction)
    rotate = anim.get("rotate", "0").strip()
    if rotate == "auto":
        turn = angle
    elif rotate == "auto-reverse":
        turn = angle + 180.0
    else:
        nums = parse_numbers(rotate)
        turn = nums[0] if nums else 0.0
    return f"translate({format_number(x)} {format_number(y)}) rotate({format_number(turn)})"
