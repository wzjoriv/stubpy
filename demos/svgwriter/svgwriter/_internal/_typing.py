"""Shared type aliases, type variables and version shims."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    NamedTuple,
    NewType,
    ParamSpec,
    TypeAlias,
    TypeVar,
)

if TYPE_CHECKING or sys.version_info >= (3, 11):
    from typing import NotRequired, Required, Self
else:

    class _Passthrough:
        """Runtime stand-in for typing forms missing on 3.10."""

        def __getitem__(self, item: Any) -> Any:
            return item

    Required = NotRequired = _Passthrough()
    Self = TypeVar("Self")

if sys.version_info >= (3, 12):
    from ._aliases312 import Matrix6, Pair, Stack
else:
    from ._stack import Stack

    _T = TypeVar("_T")
    Pair = tuple[_T, _T]
    Matrix6 = tuple[float, float, float, float, float, float]

__all__ = [
    "Align",
    "AnyPath",
    "ElementId",
    "FillRule",
    "LengthAdjust",
    "LineCap",
    "LineJoin",
    "Matrix6",
    "N",
    "NotRequired",
    "Number",
    "Opacity",
    "P",
    "Pair",
    "Points",
    "R",
    "Required",
    "Self",
    "SpreadMethod",
    "Stack",
    "T",
    "Units",
    "ValueRange",
]


class ValueRange(NamedTuple):
    """Inclusive bounds metadata for ``Annotated`` numbers."""

    low: float
    high: float


T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")
N = TypeVar("N", int, float)

Number: TypeAlias = int | float
AnyPath: TypeAlias = "str | os.PathLike[str]"
Points: TypeAlias = Iterable[tuple[float, float]]
Opacity = Annotated[float, ValueRange(0.0, 1.0)]
ElementId = NewType("ElementId", str)

LineCap = Literal["butt", "round", "square", "inherit"]
LineJoin = Literal["miter", "round", "bevel", "inherit"]
FillRule = Literal["nonzero", "evenodd", "inherit"]
Units = Literal["userSpaceOnUse", "objectBoundingBox"]
SpreadMethod = Literal["pad", "reflect", "repeat"]
LengthAdjust = Literal["spacing", "spacingAndGlyphs"]
Align = Literal[
    "none",
    "xMinYMin", "xMidYMin", "xMaxYMin",
    "xMinYMid", "xMidYMid", "xMaxYMid",
    "xMinYMax", "xMidYMax", "xMaxYMax",
]
