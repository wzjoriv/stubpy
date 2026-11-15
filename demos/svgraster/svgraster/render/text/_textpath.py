"""Arc-length measurement of a ``textPath`` reference path."""
from __future__ import annotations

import math

import numpy as np

from ...parse.flatten import flatten_path
from .._geometry import node_transform, shape_path

MEASURE_TOLERANCE = 0.05


class PathMeasure:
    """Points and tangent angles at distances along a flattened path."""

    def __init__(self, path_node, viewport):
        m = node_transform(path_node)
        lines = flatten_path(shape_path(path_node, viewport), MEASURE_TOLERANCE)
        pts = [m.apply_points(p.points) for p in lines if len(p.points) >= 2]
        if lines and lines[0].closed and pts:
            pts[0] = np.vstack([pts[0], pts[0][:1]])
        self.points = pts[0] if pts else np.zeros((0, 2))
        seg = np.hypot(*np.diff(self.points, axis=0).T) if len(self.points) > 1 else np.zeros(0)
        self.cumulative = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.cumulative[-1]) if len(self.cumulative) else 0.0

    def at(self, distance: float) -> tuple[float, float, float] | None:
        """``(x, y, angle in degrees)`` at ``distance``, or ``None`` when off the path."""
        if self.length <= 0 or distance < 0 or distance > self.length:
            return None
        i = int(np.searchsorted(self.cumulative, distance, side="right")) - 1
        i = min(max(i, 0), len(self.points) - 2)
        span = self.cumulative[i + 1] - self.cumulative[i]
        t = (distance - self.cumulative[i]) / span if span > 0 else 0.0
        p0, p1 = self.points[i], self.points[i + 1]
        x, y = p0 + (p1 - p0) * t
        return float(x), float(y), math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
