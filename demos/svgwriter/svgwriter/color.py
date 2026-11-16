"""RGB colors and the ``<paint>`` type used by ``fill`` and ``stroke``."""

from __future__ import annotations

import colorsys
import enum
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Final, TypeAlias, Union

from ._internal._typing import N
from .attributes.values import DEFAULT_PRECISION, FuncIRI

if TYPE_CHECKING:
    from .elements.base import Element

__all__ = ["Color", "PaintKeyword", "PaintValue", "clamp", "parse_color", "parse_paint"]

NAMED: Final = {"black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "gold": (255, 215, 0), "tomato": (255, 99, 71)}
_URL_RE: Final = re.compile(r"^\s*url\(\s*(['\"]?)(.*?)\1\s*\)\s*$")


def clamp(value: N, low: N, high: N) -> N:
    """Clamp *value* into ``[low, high]``."""
    return max(low, min(high, value))


@dataclass(frozen=True)
class Color:
    """An sRGB color with 8-bit channels.

    >>> Color.parse("#f80").hex
    '#ff8800'
    """

    r: int
    g: int
    b: int
    name: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not all(0 <= c <= 255 for c in (self.r, self.g, self.b)):
            raise ValueError("channels must be within 0..255")

    @classmethod
    def parse(cls, text: str) -> Color:
        return parse_color(text)

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    @property
    def hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(*self.rgb)

    @cached_property
    def hsl(self) -> tuple[float, float, float]:
        """Hue in degrees, saturation and lightness in ``0..1``."""
        h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in self.rgb))
        return (h * 360.0, s, l)

    def mix(self, other: Color, amount: float = 0.5) -> Color:
        return Color(*(round(a + (b - a) * clamp(amount, 0.0, 1.0)) for a, b in zip(self.rgb, other.rgb)))

    def __add__(self, other: Color | str) -> Color:
        return self.mix(parse_color(other) if isinstance(other, str) else other)

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return self.name or self.hex

    def __str__(self) -> str:
        return self.svg_value()


class PaintKeyword(str, enum.Enum):
    NONE = "none"
    CURRENT_COLOR = "currentColor"
    INHERIT = "inherit"


Paint: TypeAlias = Color | PaintKeyword | FuncIRI
PaintValue: TypeAlias = Union[Paint, str, "Element", None]


def parse_color(text: str) -> Color:
    """Parse a keyword, ``#rgb``, ``#rrggbb`` or ``rgb(r, g, b)`` color."""
    source = text.strip().lower()
    if source in NAMED:
        return Color(*NAMED[source], name=source)
    if source.startswith("#") and len(source) in (4, 7):
        digits = source[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return Color(*(int(digits[i : i + 2], 16) for i in (0, 2, 4)))
    match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", source)
    if match:
        return Color(*(int(g) for g in match.groups()))
    raise ValueError(f"invalid color: {text!r}")


def parse_paint(text: str) -> Paint:
    """Parse a ``fill`` or ``stroke`` value."""
    source = text.strip()
    for keyword in PaintKeyword:
        if source == keyword.value:
            return keyword
    match = _URL_RE.match(source)
    return FuncIRI(match.group(2)) if match else parse_color(source)
