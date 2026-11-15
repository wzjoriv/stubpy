"""RGB colors and the SVG 1.1 color syntax."""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field, replace
from functools import cached_property, lru_cache
from typing import Final, overload

from .._internal._constants import DEFAULT_PRECISION
from .._internal._typing import N, Opacity
from ._named import NAMED_COLORS

__all__ = ["Color", "clamp", "parse_color"]

CHANNEL_MAX: Final = 255
PERCENT_MAX: Final = 100.0
HEX_SHORT_LENGTH: Final = 3
HEX_LONG_LENGTH: Final = 6
DEGREES: Final = 360.0
SRGB_THRESHOLD: Final = 0.03928
SRGB_LINEAR_SLOPE: Final = 12.92
SRGB_OFFSET: Final = 0.055
SRGB_GAMMA: Final = 2.4
LUMA_WEIGHTS: Final = (0.2126, 0.7152, 0.0722)

_RGB_RE: Final = re.compile(r"^rgb\(\s*([^,\s]+)\s*,\s*([^,\s]+)\s*,\s*([^,\s)]+)\s*\)$")
_ICC_RE: Final = re.compile(r"\s+(icc-color\([^)]*\))\s*$")


def clamp(value: N, low: N, high: N) -> N:
    """Clamp *value* into ``[low, high]``."""
    return max(low, min(high, value))


@dataclass(frozen=True)
class Color:
    """An sRGB color with 8-bit channels.

    Parameters
    ----------
    r, g, b : int
        Channel values in ``0..255``.
    icc : str, optional
        An ``icc-color(...)`` specification kept alongside the sRGB fallback.
    name : str, optional
        Keyword to emit instead of hex when the color came from a name.

    Examples
    --------
    >>> Color.parse("#f80").hex
    '#ff8800'
    >>> str(Color(255, 0, 0).mix(Color(0, 0, 255)))
    '#800080'
    >>> str(Color.parse("red") + "blue")
    '#800080'
    >>> str(Color.parse("white") * 0.5)
    '#808080'
    """

    r: int
    g: int
    b: int
    icc: str | None = None
    name: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        for label, channel in zip("rgb", (self.r, self.g, self.b)):
            if not 0 <= channel <= CHANNEL_MAX:
                raise ValueError(f"channel {label}={channel} is outside 0..{CHANNEL_MAX}")

    @classmethod
    def parse(cls, text: str) -> Color:
        return parse_color(text)

    @classmethod
    def from_floats(cls, r: float, g: float, b: float) -> Color:
        """Build from channels in ``0.0..1.0``."""
        return cls(*(round(clamp(c, 0.0, 1.0) * CHANNEL_MAX) for c in (r, g, b)))

    @classmethod
    def from_hsl(cls, hue: float, saturation: float, lightness: float) -> Color:
        """Build from hue in degrees and saturation/lightness in ``0..1``."""
        r, g, b = colorsys.hls_to_rgb((hue % DEGREES) / DEGREES, lightness, saturation)
        return cls.from_floats(r, g, b)

    @property
    def rgb(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    @property
    def hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(*self.rgb)

    @cached_property
    def hsl(self) -> tuple[float, float, float]:
        """Hue in degrees, saturation and lightness in ``0..1``."""
        h, l, s = colorsys.rgb_to_hls(*(c / CHANNEL_MAX for c in self.rgb))
        return (h * DEGREES, s, l)

    @property
    def luminance(self) -> float:
        """Relative luminance per WCAG."""

        def linear(c: int) -> float:
            v = c / CHANNEL_MAX
            if v <= SRGB_THRESHOLD:
                return v / SRGB_LINEAR_SLOPE
            return ((v + SRGB_OFFSET) / (1 + SRGB_OFFSET)) ** SRGB_GAMMA

        return sum(w * linear(c) for w, c in zip(LUMA_WEIGHTS, self.rgb))

    def lighten(self, amount: Opacity) -> Color:
        h, s, l = self.hsl
        return Color.from_hsl(h, s, clamp(l + amount, 0.0, 1.0))

    def darken(self, amount: Opacity) -> Color:
        return self.lighten(-amount)

    def mix(self, other: Color, weight: Opacity = 0.5) -> Color:
        """Linear blend; ``weight`` is the share of *other*."""
        channels = (
            round(a + (b - a) * weight) for a, b in zip(self.rgb, other.rgb)
        )
        return Color(*channels)

    def scale(self, factor: float) -> Color:
        """Multiply every channel by *factor*, clamping to ``0..255``."""
        return Color(*(round(clamp(c * factor, 0, CHANNEL_MAX)) for c in self.rgb))

    def __add__(self, other: Color | str) -> Color:
        """Even mix of two colors."""
        if isinstance(other, str):
            other = parse_color(other)
        if not isinstance(other, Color):
            return NotImplemented
        return self.mix(other)

    def __radd__(self, other: Color | str) -> Color:
        if isinstance(other, str):
            return parse_color(other).mix(self)
        return NotImplemented

    @overload
    def __mul__(self, factor: float) -> Color: ...
    @overload
    def __mul__(self, factor: Color) -> Color: ...
    def __mul__(self, factor: float | Color) -> Color:
        """Scale by a number, or multiply channel-wise by another color."""
        if isinstance(factor, Color):
            return Color(*(round(a * b / CHANNEL_MAX) for a, b in zip(self.rgb, factor.rgb)))
        if isinstance(factor, (int, float)):
            return self.scale(factor)
        return NotImplemented

    def __rmul__(self, factor: float) -> Color:
        if isinstance(factor, (int, float)):
            return self.scale(factor)
        return NotImplemented

    def __truediv__(self, divisor: float) -> Color:
        if isinstance(divisor, (int, float)):
            return self.scale(1.0 / divisor)
        return NotImplemented

    def with_icc(self, spec: str) -> Color:
        return replace(self, icc=spec)

    def to_percent(self) -> str:
        """Render as ``rgb(100%,50%,0%)``."""
        parts = (f"{c * PERCENT_MAX / CHANNEL_MAX:g}%" for c in self.rgb)
        return "rgb({})".format(",".join(parts))

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        text = self.name or self.hex
        return f"{text} {self.icc}" if self.icc else text

    def __str__(self) -> str:
        return self.svg_value()


def _channel(token: str) -> int:
    if token.endswith("%"):
        return round(clamp(float(token[:-1]), 0.0, PERCENT_MAX) * CHANNEL_MAX / PERCENT_MAX)
    return clamp(int(token), 0, CHANNEL_MAX)


@lru_cache(maxsize=256)
def parse_color(text: str) -> Color:
    """Parse a color keyword, ``#rgb``, ``#rrggbb`` or ``rgb(...)``.

    An optional trailing ``icc-color(...)`` is preserved.
    """
    source = text.strip()
    icc = None
    match = _ICC_RE.search(source)
    if match:
        icc = match.group(1)
        source = source[: match.start()]
    lowered = source.lower()
    if lowered in NAMED_COLORS:
        return Color(*NAMED_COLORS[lowered], icc=icc, name=lowered)
    if lowered.startswith("#"):
        digits = lowered[1:]
        if len(digits) == HEX_SHORT_LENGTH:
            digits = "".join(d * 2 for d in digits)
        if len(digits) != HEX_LONG_LENGTH:
            raise ValueError(f"invalid hex color: {text!r}")
        return Color(int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), icc=icc)
    rgb = _RGB_RE.match(lowered)
    if rgb:
        tokens = rgb.groups()
        if len({t.endswith("%") for t in tokens}) != 1:
            raise ValueError(f"mixed integer and percent channels: {text!r}")
        return Color(*(_channel(t) for t in tokens), icc=icc)
    raise ValueError(f"unknown color: {text!r}")
