"""Lengths with units (``10``, ``2.5mm``, ``50%``)."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from functools import lru_cache, partial
from typing import Final, TypeAlias, overload

from .values import DEFAULT_PRECISION, format_number

__all__ = ["Length", "LengthLike", "Unit", "cm", "em", "inch", "mm", "percent", "pt", "px"]


class Unit(str, enum.Enum):
    """SVG 1.1 length units."""

    NONE = ""
    PX = "px"
    PT = "pt"
    MM = "mm"
    CM = "cm"
    IN = "in"
    EM = "em"
    PERCENT = "%"
    USER = ""
    INCH = "in"

    def __str__(self) -> str:
        return self.value


DPI: Final = 96.0
_PER_INCH: Final = {Unit.IN: 1.0, Unit.PT: 72.0, Unit.MM: 25.4, Unit.CM: 2.54}
_LENGTH_RE: Final = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+))\s*(px|pt|mm|cm|in|em|%)?\s*$")


@dataclass(frozen=True, slots=True)
class Length:
    """A number with an optional unit.

    >>> str(Length(2.5, Unit.MM))
    '2.5mm'
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

    def to_user_units(self, *, font_size: float = 16.0) -> float:
        if self.unit in (Unit.NONE, Unit.PX):
            return self.value
        if self.unit is Unit.EM:
            return self.value * font_size
        if self.unit is Unit.PERCENT:
            raise ValueError("percentage lengths need a reference length")
        return self.value * DPI / _PER_INCH[self.unit]

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return format_number(self.value, precision) + self.unit.value

    def __str__(self) -> str:
        return self.svg_value()

    def __add__(self, other: Length | float) -> Length:
        other = Length.parse(other)
        if other.unit is not self.unit and other.unit is not Unit.NONE:
            raise ValueError(f"cannot add {self.unit!s} and {other.unit!s}")
        return Length(self.value + other.value, self.unit)

    def __mul__(self, factor: float) -> Length:
        return Length(self.value * factor, self.unit)

    __rmul__ = __mul__


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
mm = partial(Length, unit=Unit.MM)
cm = partial(Length, unit=Unit.CM)
inch = partial(Length, unit=Unit.IN)
em = partial(Length, unit=Unit.EM)
percent = partial(Length, unit=Unit.PERCENT)
