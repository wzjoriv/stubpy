"""2-D affine matrices in SVG's ``[a b c d e f]`` layout."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, NamedTuple

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number
from .._internal._typing import Matrix6

__all__ = ["IDENTITY", "Matrix", "Point"]

EPSILON: Final = 1e-12


class Point(NamedTuple):
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Matrix:
    """An affine transform ``[a c e; b d f; 0 0 1]``.

    Matrices compose with ``@`` in SVG order: ``m1 @ m2`` applies ``m2``
    first, matching ``transform="m1 m2"``.

    Examples
    --------
    >>> (Matrix.translate(10, 0) @ Matrix.scale(2)).apply(1, 1)
    Point(x=12.0, y=2.0)
    """

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def translate(cls, tx: float, ty: float = 0.0) -> Matrix:
        return cls(1.0, 0.0, 0.0, 1.0, tx, ty)

    @classmethod
    def scale(cls, sx: float, sy: float | None = None) -> Matrix:
        return cls(sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)

    @classmethod
    def rotate(cls, angle: float, cx: float = 0.0, cy: float = 0.0) -> Matrix:
        rad = math.radians(angle)
        cos, sin = math.cos(rad), math.sin(rad)
        rotation = cls(cos, sin, -sin, cos, 0.0, 0.0)
        if cx or cy:
            return cls.translate(cx, cy) @ rotation @ cls.translate(-cx, -cy)
        return rotation

    @classmethod
    def skew_x(cls, angle: float) -> Matrix:
        return cls(1.0, 0.0, math.tan(math.radians(angle)), 1.0, 0.0, 0.0)

    @classmethod
    def skew_y(cls, angle: float) -> Matrix:
        return cls(1.0, math.tan(math.radians(angle)), 0.0, 1.0, 0.0, 0.0)

    def __matmul__(self, other: Matrix) -> Matrix:
        return Matrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    @property
    def determinant(self) -> float:
        return self.a * self.d - self.b * self.c

    @property
    def is_identity(self) -> bool:
        return self.isclose(IDENTITY)

    def inverse(self) -> Matrix:
        det = self.determinant
        if abs(det) < EPSILON:
            raise ValueError("matrix is not invertible")
        return Matrix(
            self.d / det,
            -self.b / det,
            -self.c / det,
            self.a / det,
            (self.c * self.f - self.d * self.e) / det,
            (self.b * self.e - self.a * self.f) / det,
        )

    def apply(self, x: float, y: float) -> Point:
        return Point(self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def as_tuple(self) -> Matrix6:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def isclose(self, other: Matrix, tolerance: float = 1e-9) -> bool:
        return all(math.isclose(x, y, abs_tol=tolerance) for x, y in zip(self.as_tuple(), other.as_tuple()))

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return "matrix({})".format(" ".join(format_number(v, precision) for v in self.as_tuple()))


IDENTITY: Final = Matrix()
