"""The six SVG transform functions as value objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number
from .matrix import Matrix

__all__ = ["MatrixOp", "Rotate", "Scale", "SkewX", "SkewY", "TransformOp", "Translate"]


class TransformOp(ABC):
    """One entry of a ``transform`` list."""

    keyword: ClassVar[str]

    @property
    @abstractmethod
    def arguments(self) -> tuple[float, ...]:
        """The numbers written inside the parentheses."""

    @abstractmethod
    def to_matrix(self) -> Matrix: ...

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        args = " ".join(format_number(a, precision) for a in self.arguments)
        return f"{self.keyword}({args})"

    def __str__(self) -> str:
        return self.svg_value()


@dataclass(frozen=True)
class Translate(TransformOp):
    keyword: ClassVar[str] = "translate"
    tx: float
    ty: float = 0.0

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.tx,) if self.ty == 0 else (self.tx, self.ty)

    def to_matrix(self) -> Matrix:
        return Matrix.translate(self.tx, self.ty)


@dataclass(frozen=True)
class Scale(TransformOp):
    keyword: ClassVar[str] = "scale"
    sx: float
    sy: float | None = None

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.sx,) if self.sy is None else (self.sx, self.sy)

    def to_matrix(self) -> Matrix:
        return Matrix.scale(self.sx, self.sy)


@dataclass(frozen=True)
class Rotate(TransformOp):
    keyword: ClassVar[str] = "rotate"
    angle: float
    cx: float = 0.0
    cy: float = 0.0

    @property
    def arguments(self) -> tuple[float, ...]:
        if self.cx == 0 and self.cy == 0:
            return (self.angle,)
        return (self.angle, self.cx, self.cy)

    def to_matrix(self) -> Matrix:
        return Matrix.rotate(self.angle, self.cx, self.cy)


@dataclass(frozen=True)
class SkewX(TransformOp):
    keyword: ClassVar[str] = "skewX"
    angle: float

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.angle,)

    def to_matrix(self) -> Matrix:
        return Matrix.skew_x(self.angle)


@dataclass(frozen=True)
class SkewY(TransformOp):
    keyword: ClassVar[str] = "skewY"
    angle: float

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.angle,)

    def to_matrix(self) -> Matrix:
        return Matrix.skew_y(self.angle)


@dataclass(frozen=True)
class MatrixOp(TransformOp):
    keyword: ClassVar[str] = "matrix"
    matrix: Matrix

    @property
    def arguments(self) -> tuple[float, ...]:
        return self.matrix.as_tuple()

    def to_matrix(self) -> Matrix:
        return self.matrix
