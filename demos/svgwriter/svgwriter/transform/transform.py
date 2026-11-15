"""Transform lists: parsing, building and composition."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Final, overload

from .._internal._constants import DEFAULT_PRECISION
from .._internal._hybrid import hybridmethod
from .matrix import Matrix, Point
from .ops import MatrixOp, Rotate, Scale, SkewX, SkewY, TransformOp, Translate

__all__ = ["Transform", "TransformLike", "as_transform", "parse_transform"]

_FUNCTION_RE: Final = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_NUMBER_RE: Final = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_ARITY: Final = {
    "matrix": (6,),
    "translate": (1, 2),
    "scale": (1, 2),
    "rotate": (1, 3),
    "skewX": (1,),
    "skewY": (1,),
}


class Transform:
    """An ordered list of transform operations.

    Builder methods append and return ``self``; called on the class they
    start a new list. ``@`` concatenates in SVG order (the right operand is
    applied first) and also accepts single operations and matrices.

    Examples
    --------
    >>> str(Transform().translate(10, 20).rotate(45))
    'translate(10 20) rotate(45)'
    >>> str(Transform.rotate(30) @ Transform.scale(2))
    'rotate(30) scale(2)'
    >>> Transform.translate(5) @ (1, 1)
    Point(x=6.0, y=1.0)
    """

    __slots__ = ("_ops",)

    def __init__(self, ops: Iterable[TransformOp] = ()) -> None:
        self._ops: list[TransformOp] = list(ops)

    @classmethod
    def parse(cls, text: str) -> Transform:
        return parse_transform(text)

    @hybridmethod
    def translate(self, tx: float, ty: float = 0.0) -> None:
        self._ops.append(Translate(tx, ty))

    @hybridmethod
    def scale(self, sx: float, sy: float | None = None) -> None:
        self._ops.append(Scale(sx, sy))

    @hybridmethod
    def rotate(self, angle: float, cx: float = 0.0, cy: float = 0.0) -> None:
        self._ops.append(Rotate(angle, cx, cy))

    @hybridmethod
    def skew_x(self, angle: float) -> None:
        self._ops.append(SkewX(angle))

    @hybridmethod
    def skew_y(self, angle: float) -> None:
        self._ops.append(SkewY(angle))

    @hybridmethod
    def matrix(self, a: float, b: float, c: float, d: float, e: float, f: float) -> None:
        self._ops.append(MatrixOp(Matrix(a, b, c, d, e, f)))

    def to_matrix(self) -> Matrix:
        """Collapse the list into a single matrix."""
        result = Matrix()
        for op in self._ops:
            result = result @ op.to_matrix()
        return result

    def apply(self, x: float, y: float) -> Point:
        return self.to_matrix().apply(x, y)

    def simplified(self) -> Transform:
        """Return an equivalent single ``matrix(...)`` transform."""
        return Transform([MatrixOp(self.to_matrix())])

    @overload
    def __matmul__(self, other: Transform | TransformOp | Matrix) -> Transform: ...
    @overload
    def __matmul__(self, other: Point | tuple[float, float]) -> Point: ...
    def __matmul__(self, other: Transform | TransformOp | Matrix | Point | tuple[float, float]) -> Transform | Point:
        if isinstance(other, tuple):
            return self.apply(*other)
        if isinstance(other, (Transform, TransformOp, Matrix)):
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

    def inverse(self) -> Transform:
        """The inverse as a single ``matrix(...)``."""
        return Transform([MatrixOp(self.to_matrix().inverse())])

    def __iter__(self) -> Iterator[TransformOp]:
        return iter(self._ops)

    def __len__(self) -> int:
        return len(self._ops)

    @overload
    def __getitem__(self, index: int) -> TransformOp: ...
    @overload
    def __getitem__(self, index: slice) -> Transform: ...
    def __getitem__(self, index: int | slice) -> TransformOp | Transform:
        if isinstance(index, slice):
            return Transform(self._ops[index])
        return self._ops[index]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Transform) and self._ops == other._ops

    def __hash__(self) -> int:
        return hash(tuple(self._ops))

    def __repr__(self) -> str:
        return f"Transform({self})"

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return " ".join(op.svg_value(precision) for op in self._ops)

    def __str__(self) -> str:
        return self.svg_value()


TransformLike = Transform | TransformOp | Matrix | str


def _make_op(name: str, args: list[float]) -> TransformOp:
    if name == "matrix":
        return MatrixOp(Matrix(*args))
    if name == "translate":
        return Translate(*args)
    if name == "scale":
        return Scale(*args)
    if name == "rotate":
        return Rotate(*args)
    return SkewX(*args) if name == "skewX" else SkewY(*args)


def parse_transform(text: str) -> Transform:
    """Parse a ``transform`` attribute value."""
    ops = []
    position = 0
    for match in _FUNCTION_RE.finditer(text):
        if text[position:match.start()].strip(" \t\r\n,"):
            raise ValueError(f"invalid transform: {text!r}")
        position = match.end()
        name, body = match.groups()
        args = [float(n) for n in _NUMBER_RE.findall(body)]
        if len(args) not in _ARITY[name]:
            expected = " or ".join(str(n) for n in _ARITY[name])
            raise ValueError(f"{name}() takes {expected} arguments, got {len(args)}: {text!r}")
        ops.append(_make_op(name, args))
    if text[position:].strip(" \t\r\n,"):
        raise ValueError(f"invalid transform: {text!r}")
    return Transform(ops)


def as_transform(value: TransformLike) -> Transform:
    """Coerce strings, single ops and matrices into a ``Transform``."""
    if isinstance(value, Transform):
        return value
    if isinstance(value, TransformOp):
        return Transform([value])
    if isinstance(value, Matrix):
        return Transform([MatrixOp(value)])
    return parse_transform(value)
