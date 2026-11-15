"""Lengths with units (``10``, ``2.5mm``, ``50%``)."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from functools import lru_cache, partial
from typing import Final, TypeAlias, overload

from .._internal._constants import (
    CM_PER_INCH,
    DEFAULT_DPI,
    DEFAULT_FONT_SIZE,
    DEFAULT_PRECISION,
    EX_PER_EM,
    MM_PER_INCH,
    PC_PER_INCH,
    PT_PER_INCH,
)
from .._internal._speedups import format_number

__all__ = [
    "Length",
    "LengthLike",
    "Unit",
    "cm",
    "em",
    "ex",
    "inch",
    "mm",
    "pc",
    "percent",
    "pt",
    "px",
]


class Unit(str, enum.Enum):
    """SVG 1.1 length units."""

    NONE = ""
    PX = "px"
    PT = "pt"
    PC = "pc"
    MM = "mm"
    CM = "cm"
    IN = "in"
    EM = "em"
    EX = "ex"
    PERCENT = "%"
    USER = ""
    PIXEL = "px"
    INCH = "in"

    def __str__(self) -> str:
        return self.value


_ABSOLUTE_PER_INCH: Final = {
    Unit.IN: 1.0,
    Unit.PT: PT_PER_INCH,
    Unit.PC: PC_PER_INCH,
    Unit.MM: MM_PER_INCH,
    Unit.CM: CM_PER_INCH,
}
_LENGTH_RE: Final = re.compile(
    r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*(px|pt|pc|mm|cm|in|em|ex|%)?\s*$"
)


@dataclass(frozen=True, slots=True)
class Length:
    """A number with an optional unit.

    Parameters
    ----------
    value : float
        The magnitude.
    unit : Unit, optional
        The unit; ``Unit.NONE`` means user units.

    Examples
    --------
    >>> str(Length(2.5, Unit.MM))
    '2.5mm'
    >>> Length.parse("1in").to_user_units()
    96.0
    """

    value: float
    unit: Unit = Unit.NONE

    @overload
    @classmethod
    def parse(cls, text: str) -> Length: ...
    @overload
    @classmethod
    def parse(cls, text: float) -> Length: ...
    @overload
    @classmethod
    def parse(cls, text: Length) -> Length: ...
    @classmethod
    def parse(cls, text: str | float | Length) -> Length:
        """Parse ``"12.5mm"``; numbers and lengths pass through."""
        if isinstance(text, Length):
            return text
        if isinstance(text, (int, float)):
            return cls(float(text))
        return _parse_cached(text)

    def to_user_units(
        self,
        *,
        dpi: float = DEFAULT_DPI,
        font_size: float = DEFAULT_FONT_SIZE,
        reference: float | None = None,
    ) -> float:
        """Convert to user units (pixels).

        ``reference`` is the length that ``100%`` resolves to.
        """
        if self.unit in (Unit.NONE, Unit.PX):
            return self.value
        if self.unit is Unit.EM:
            return self.value * font_size
        if self.unit is Unit.EX:
            return self.value * font_size * EX_PER_EM
        if self.unit is Unit.PERCENT:
            if reference is None:
                raise ValueError("percentage lengths need a reference length")
            return self.value * reference / 100.0
        return self.value * dpi / _ABSOLUTE_PER_INCH[self.unit]

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return format_number(self.value, precision) + self.unit.value

    def __str__(self) -> str:
        return self.svg_value()

    def __float__(self) -> float:
        return self.to_user_units()

    def __add__(self, other: Length | float) -> Length:
        other = Length.parse(other)
        if other.unit is not self.unit and other.unit is not Unit.NONE:
            raise ValueError(f"cannot add {self.unit!s} and {other.unit!s}")
        return Length(self.value + other.value, self.unit)

    def __mul__(self, factor: float) -> Length:
        return Length(self.value * factor, self.unit)

    __rmul__ = __mul__

    def __neg__(self) -> Length:
        return Length(-self.value, self.unit)


LengthLike: TypeAlias = Length | float | int | str


@lru_cache(maxsize=512)
def _parse_cached(text: str) -> Length:
    match = _LENGTH_RE.match(text)
    if match is None:
        raise ValueError(f"invalid length: {text!r}")
    number, unit = match.groups()
    return Length(float(number), Unit(unit or ""))


px = partial(Length, unit=Unit.PX)
pt = partial(Length, unit=Unit.PT)
pc = partial(Length, unit=Unit.PC)
mm = partial(Length, unit=Unit.MM)
cm = partial(Length, unit=Unit.CM)
inch = partial(Length, unit=Unit.IN)
em = partial(Length, unit=Unit.EM)
ex = partial(Length, unit=Unit.EX)
percent = partial(Length, unit=Unit.PERCENT)
