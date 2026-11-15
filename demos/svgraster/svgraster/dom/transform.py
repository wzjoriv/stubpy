"""2-D affine matrices and the SVG ``transform`` attribute grammar."""
from __future__ import annotations

import math
import re
from typing import NamedTuple

import numpy as np

_TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
SINGULAR_EPS = 1e-12


class Matrix(NamedTuple):
    """The affine map ``(x, y) -> (a*x + c*y + e, b*x + d*y + f)``."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def translate(cls, tx: float, ty: float = 0.0) -> Matrix:
        """A translation."""
        return cls(1.0, 0.0, 0.0, 1.0, tx, ty)

    @classmethod
    def scale(cls, sx: float, sy: float | None = None) -> Matrix:
        """A scale; ``sy`` defaults to ``sx``."""
        return cls(sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)

    @classmethod
    def rotate(cls, degrees: float, cx: float = 0.0, cy: float = 0.0) -> Matrix:
        """A rotation about ``(cx, cy)``."""
        rad = math.radians(degrees)
        cos, sin = math.cos(rad), math.sin(rad)
        rot = cls(cos, sin, -sin, cos, 0.0, 0.0)
        if cx or cy:
            return cls.translate(cx, cy) @ rot @ cls.translate(-cx, -cy)
        return rot

    @classmethod
    def skew_x(cls, degrees: float) -> Matrix:
        """A horizontal skew."""
        return cls(1.0, 0.0, math.tan(math.radians(degrees)), 1.0, 0.0, 0.0)

    @classmethod
    def skew_y(cls, degrees: float) -> Matrix:
        """A vertical skew."""
        return cls(1.0, math.tan(math.radians(degrees)), 0.0, 1.0, 0.0, 0.0)

    def __matmul__(self, other: Matrix) -> Matrix:  # type: ignore[override]
        """Compose so that ``(self @ other)(p) == self(other(p))``."""
        a1, b1, c1, d1, e1, f1 = self
        a2, b2, c2, d2, e2, f2 = other
        return Matrix(
            a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1,
        )

    @property
    def determinant(self) -> float:
        """The determinant of the linear part."""
        return self.a * self.d - self.b * self.c

    @property
    def is_invertible(self) -> bool:
        """Whether the matrix can be inverted."""
        return abs(self.determinant) > SINGULAR_EPS

    def inverse(self) -> Matrix:
        """The inverse map."""
        det = self.determinant
        if abs(det) <= SINGULAR_EPS:
            raise ValueError("matrix is not invertible")
        a, b, c, d, e, f = self
        return Matrix(d / det, -b / det, -c / det, a / det,
                      (c * f - d * e) / det, (b * e - a * f) / det)

    @property
    def mean_scale(self) -> float:
        """The geometric-mean scale factor."""
        return math.sqrt(abs(self.determinant))

    @property
    def axis_scales(self) -> tuple[float, float]:
        """The lengths of the transformed unit x and y vectors."""
        return math.hypot(self.a, self.b), math.hypot(self.c, self.d)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        """Transform one point."""
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def apply_vector(self, x: float, y: float) -> tuple[float, float]:
        """Transform a direction (ignores translation)."""
        return (self.a * x + self.c * y, self.b * x + self.d * y)

    def apply_points(self, points: np.ndarray) -> np.ndarray:
        """Transform an ``(N, 2)`` array of points."""
        pts = np.asarray(points, dtype=np.float64)
        out = np.empty_like(pts)
        out[:, 0] = self.a * pts[:, 0] + self.c * pts[:, 1] + self.e
        out[:, 1] = self.b * pts[:, 0] + self.d * pts[:, 1] + self.f
        return out

    def as_array(self) -> np.ndarray:
        """The ``2x3`` row-major array ``[[a, c, e], [b, d, f]]``."""
        return np.array([[self.a, self.c, self.e], [self.b, self.d, self.f]], dtype=np.float64)

    def transform_rect(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        """Axis-aligned bounds ``(x0, y0, x1, y1)`` of a transformed rectangle."""
        pts = self.apply_points(np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]))
        return (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())


IDENTITY = Matrix()


def parse_transform(text: str | None) -> Matrix:
    """Parse an SVG transform list into a single matrix."""
    result = IDENTITY
    if not text:
        return result
    for name, args in _TRANSFORM_RE.findall(text):
        nums = [float(n) for n in _NUMBER_RE.findall(args)]
        if name == "matrix" and len(nums) == 6:
            step = Matrix(*nums)
        elif name == "translate" and nums:
            step = Matrix.translate(nums[0], nums[1] if len(nums) > 1 else 0.0)
        elif name == "scale" and nums:
            step = Matrix.scale(nums[0], nums[1] if len(nums) > 1 else None)
        elif name == "rotate" and nums:
            step = Matrix.rotate(nums[0], *(nums[1:3] if len(nums) >= 3 else ()))
        elif name == "skewX" and nums:
            step = Matrix.skew_x(nums[0])
        elif name == "skewY" and nums:
            step = Matrix.skew_y(nums[0])
        else:
            continue
        result = result @ step
    return result
