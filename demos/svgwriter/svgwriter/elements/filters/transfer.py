"""``feComponentTransfer`` and its ``feFuncR/G/B/A`` children."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any

from ..._internal._typing import Self
from .._mixins import CoreAttributes
from ..base import ContentModel
from ..container import Container
from .base import SingleInput

__all__ = ["FeComponentTransfer", "FeFunc", "FeFuncA", "FeFuncB", "FeFuncG", "FeFuncR", "TransferType"]


def _numbers(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    return [float(v) for v in str(value).replace(",", " ").split()]


class TransferType(str, enum.Enum):
    IDENTITY = "identity"
    TABLE = "table"
    DISCRETE = "discrete"
    LINEAR = "linear"
    GAMMA = "gamma"


class FeFunc(CoreAttributes, content=ContentModel.ELEMENTS):
    """Shared base of the four channel transfer functions."""

    def __init__(
        self,
        type: TransferType = TransferType.IDENTITY,
        *,
        table_values: Sequence[float] | None = None,
        slope: float | None = None,
        intercept: float | None = None,
        amplitude: float | None = None,
        exponent: float | None = None,
        offset: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(
            type=type,
            table_values=tuple(table_values) if table_values is not None else None,
            slope=slope,
            intercept=intercept,
            amplitude=amplitude,
            exponent=exponent,
            offset=offset,
        )

    @classmethod
    def linear(cls, slope: float, intercept: float = 0, **kwargs: Any) -> Self:
        return cls(TransferType.LINEAR, slope=slope, intercept=intercept, **kwargs)

    @classmethod
    def table(cls, *values: float, **kwargs: Any) -> Self:
        return cls(TransferType.TABLE, table_values=values, **kwargs)

    @classmethod
    def gamma(cls, amplitude: float = 1, exponent: float = 1, offset: float = 0, **kwargs: Any) -> Self:
        return cls(TransferType.GAMMA, amplitude=amplitude, exponent=exponent, offset=offset, **kwargs)

    def evaluate(self, c: float) -> float:
        """Apply this transfer function to a channel value in ``0..1``."""
        kind = TransferType(self.get("type", TransferType.IDENTITY))
        table = _numbers(self.get("tableValues"))
        if kind is TransferType.LINEAR:
            return float(self.get("slope", 1)) * c + float(self.get("intercept", 0))
        if kind is TransferType.GAMMA:
            return float(self.get("amplitude", 1)) * c ** float(self.get("exponent", 1)) + float(self.get("offset", 0))
        if kind is TransferType.TABLE and len(table) > 1:
            n = len(table) - 1
            k = min(int(c * n), n - 1)
            return table[k] + (c * n - k) * (table[k + 1] - table[k])
        if kind is TransferType.DISCRETE and table:
            return table[min(int(c * len(table)), len(table) - 1)]
        return c


class FeFuncR(FeFunc, tag="feFuncR"):
    """``<feFuncR>``."""


class FeFuncG(FeFunc, tag="feFuncG"):
    """``<feFuncG>``."""


class FeFuncB(FeFunc, tag="feFuncB"):
    """``<feFuncB>``."""


class FeFuncA(FeFunc, tag="feFuncA"):
    """``<feFuncA>``."""


class FeComponentTransfer(SingleInput, Container[FeFunc], tag="feComponentTransfer"):
    """``<feComponentTransfer>``: per-channel remapping."""

    def __init__(
        self,
        *functions: FeFunc,
        red: FeFunc | None = None,
        green: FeFunc | None = None,
        blue: FeFunc | None = None,
        alpha: FeFunc | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*functions, **kwargs)
        for func, cls in ((red, FeFuncR), (green, FeFuncG), (blue, FeFuncB), (alpha, FeFuncA)):
            if func is not None:
                self.add(func if isinstance(func, cls) else cls.from_attributes(func.attributes))
