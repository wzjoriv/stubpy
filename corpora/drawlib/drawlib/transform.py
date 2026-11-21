"""Affine matrices and transform lists."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final, NamedTuple, overload

from ._internal._helpers import hybridmethod
from ._internal._typing import Matrix6
from .attributes.values import DEFAULT_PRECISION, format_number

__all__ = ["IDENTITY", "Matrix", "Point", "Transform", "TransformLike", "TransformOp", "as_transform", "parse_transform"]

_FUNCTION_RE: Final = re.compile(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)")
_NUMBER_RE: Final = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


class Point(NamedTuple):
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Matrix:
    """An affine transform ``[a c e; b d f; 0 0 1]``; ``m1 @ m2`` applies ``m2`` first.

    >>> Matrix.scale(3) @ (1, 2)
    Point(x=3.0, y=6.0)
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
    def rotate(cls, angle: float) -> Matrix:
        rad = math.radians(angle)
        return cls(math.cos(rad), math.sin(rad), -math.sin(rad), math.cos(rad))

    @overload
    def __matmul__(self, other: Matrix) -> Matrix: ...
    @overload
    def __matmul__(self, other: Point | tuple[float, float]) -> Point: ...
    def __matmul__(self, other: Matrix | Point | tuple[float, float]) -> Matrix | Point:
        if isinstance(other, tuple):
            return self.apply(*other)
        if not isinstance(other, Matrix):
            return NotImplemented
        return Matrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, x: float, y: float) -> Point:
        return Point(self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def as_tuple(self) -> Matrix6:
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return "matrix({})".format(" ".join(format_number(v, precision) for v in self.as_tuple()))


IDENTITY: Final = Matrix()


class TransformOp(NamedTuple):
    """One entry of a ``transform`` list."""

    keyword: str
    arguments: tuple[float, ...]

    def to_matrix(self) -> Matrix:
        if self.keyword == "matrix":
            return Matrix(*self.arguments)
        if self.keyword == "translate":
            return Matrix.translate(*self.arguments)
        if self.keyword == "scale":
            return Matrix.scale(*self.arguments)
        return Matrix.rotate(*self.arguments)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return f"{self.keyword}({' '.join(format_number(a, precision) for a in self.arguments)})"


class Transform:
    """An ordered list of transform operations.

    Builder methods append and return ``self``; called on the class they
    start a new list.

    >>> str(Transform().translate(10, 20).rotate(45))
    'translate(10 20) rotate(45)'
    """

    __slots__ = ("_ops",)

    def __init__(self, ops: Iterable[TransformOp] = ()) -> None:
        self._ops: list[TransformOp] = list(ops)

    @classmethod
    def parse(cls, text: str) -> Transform:
        return parse_transform(text)

    @hybridmethod
    def translate(self, tx: float, ty: float = 0.0) -> None:
        self._ops.append(TransformOp("translate", (tx, ty)))

    @hybridmethod
    def scale(self, sx: float, sy: float | None = None) -> None:
        self._ops.append(TransformOp("scale", (sx,) if sy is None else (sx, sy)))

    @hybridmethod
    def rotate(self, angle: float) -> None:
        self._ops.append(TransformOp("rotate", (angle,)))

    def to_matrix(self) -> Matrix:
        result = Matrix()
        for op in self._ops:
            result = result @ op.to_matrix()
        return result

    @overload
    def __matmul__(self, other: Transform | TransformOp | Matrix) -> Transform: ...
    @overload
    def __matmul__(self, other: Point | tuple[float, float]) -> Point: ...
    def __matmul__(self, other: Transform | TransformOp | Matrix | Point | tuple[float, float]) -> Transform | Point:
        if isinstance(other, TransformOp):
            return Transform([*self._ops, other])
        if isinstance(other, tuple):
            return self.to_matrix().apply(*other)
        if isinstance(other, (Transform, Matrix)):
            return Transform([*self._ops, *as_transform(other)._ops])
        return NotImplemented

    def __rmatmul__(self, other: TransformOp | Matrix) -> Transform:
        if isinstance(other, (TransformOp, Matrix)):
            return Transform([*as_transform(other)._ops, *self._ops])
        return NotImplemented

    def __imatmul__(self, other: Transform | TransformOp | Matrix) -> Transform:
        if not isinstance(other, (Transform, TransformOp, Matrix)):
            return NotImplemented
        self._ops.extend(as_transform(other)._ops)
        return self

    def __iter__(self) -> Iterator[TransformOp]:
        return iter(self._ops)

    def __len__(self) -> int:
        return len(self._ops)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return " ".join(op.svg_value(precision) for op in self._ops)

    def __str__(self) -> str:
        return self.svg_value()


TransformLike = Transform | TransformOp | Matrix | str


def parse_transform(text: str) -> Transform:
    """Parse a ``transform`` attribute value."""
    ops = [
        TransformOp(name, tuple(float(n) for n in _NUMBER_RE.findall(body)))
        for name, body in _FUNCTION_RE.findall(text)
    ]
    if not ops:
        raise ValueError(f"invalid transform: {text!r}")
    return Transform(ops)


def as_transform(value: TransformLike) -> Transform:
    """Coerce strings, single ops and matrices into a ``Transform``."""
    if isinstance(value, Transform):
        return value
    if isinstance(value, TransformOp):
        return Transform([value])
    if isinstance(value, Matrix):
        return Transform([TransformOp("matrix", value.as_tuple())])
    return parse_transform(value)
