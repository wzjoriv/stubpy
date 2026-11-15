"""CSS color syntax: keywords, hex, rgb()/rgba() and hsl()/hsla()."""
from __future__ import annotations

import re
from typing import NamedTuple

from ._named import NAMED_COLORS, SYSTEM_COLORS

CHANNEL_MAX = 255.0
PERCENT = 100.0
HUE_TURN = 360.0
_FUNC_RE = re.compile(r"^(rgba?|hsla?)\(\s*(.*?)\s*\)$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"[\s,/]+")


class Color(NamedTuple):
    """A non-premultiplied RGBA color with channels in [0, 1]."""

    r: float
    g: float
    b: float
    a: float = 1.0

    def with_alpha(self, factor: float) -> Color:
        """Return a copy with alpha multiplied by ``factor``."""
        return Color(self.r, self.g, self.b, self.a * factor)

    def premultiplied(self) -> tuple[float, float, float, float]:
        """Return the premultiplied ``(r, g, b, a)`` tuple."""
        return (self.r * self.a, self.g * self.a, self.b * self.a, self.a)

    def to_bytes(self) -> tuple[int, int, int, int]:
        """Return the color as 8-bit channels."""
        return tuple(int(round(_clamp(v) * CHANNEL_MAX)) for v in self)

    @classmethod
    def from_bytes(cls, r: int, g: int, b: int, a: int = 255) -> Color:
        """Build a color from 8-bit channels."""
        return cls(r / CHANNEL_MAX, g / CHANNEL_MAX, b / CHANNEL_MAX, a / CHANNEL_MAX)


TRANSPARENT = Color(0.0, 0.0, 0.0, 0.0)
BLACK = Color(0.0, 0.0, 0.0, 1.0)


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def _channel(token: str) -> float:
    if token.endswith("%"):
        return _clamp(float(token[:-1]) / PERCENT)
    return _clamp(float(token) / CHANNEL_MAX)


def _alpha(token: str) -> float:
    if token.endswith("%"):
        return _clamp(float(token[:-1]) / PERCENT)
    return _clamp(float(token))


def _hue_to_rgb(p: float, q: float, t: float) -> float:
    t %= 1.0
    if t < 1 / 6:
        return p + (q - p) * 6 * t
    if t < 1 / 2:
        return q
    if t < 2 / 3:
        return p + (q - p) * (2 / 3 - t) * 6
    return p


def hsl_to_rgb(h: float, s: float, light: float) -> tuple[float, float, float]:
    """Convert hue (degrees), saturation and lightness (0-1) to RGB."""
    h = (h % HUE_TURN) / HUE_TURN
    if s == 0:
        return (light, light, light)
    q = light * (1 + s) if light < 0.5 else light + s - light * s
    p = 2 * light - q
    return (_hue_to_rgb(p, q, h + 1 / 3), _hue_to_rgb(p, q, h), _hue_to_rgb(p, q, h - 1 / 3))


def _parse_hex(body: str) -> Color | None:
    if not re.fullmatch(r"[0-9a-fA-F]+", body):
        return None
    if len(body) in (3, 4):
        body = "".join(ch * 2 for ch in body)
    if len(body) not in (6, 8):
        return None
    values = [int(body[i:i + 2], 16) for i in range(0, len(body), 2)]
    return Color.from_bytes(*values)


def _parse_function(name: str, args: str) -> Color | None:
    parts = [p for p in _SPLIT_RE.split(args) if p]
    if len(parts) not in (3, 4):
        return None
    alpha = _alpha(parts[3]) if len(parts) == 4 else 1.0
    if name.startswith("rgb"):
        return Color(*(_channel(p) for p in parts[:3]), alpha)
    hue = float(parts[0].removesuffix("deg"))
    sat = _clamp(float(parts[1].rstrip("%")) / PERCENT)
    light = _clamp(float(parts[2].rstrip("%")) / PERCENT)
    return Color(*hsl_to_rgb(hue, sat, light), alpha)


def parse_color(text: str, current: Color = BLACK) -> Color | None:
    """Parse a CSS color, returning ``None`` for invalid input."""
    value = text.strip()
    lower = value.lower()
    if lower == "currentcolor":
        return current
    if lower == "transparent":
        return TRANSPARENT
    if lower in NAMED_COLORS:
        return Color.from_bytes(*NAMED_COLORS[lower])
    if lower in SYSTEM_COLORS:
        return Color.from_bytes(*SYSTEM_COLORS[lower])
    if value.startswith("#"):
        return _parse_hex(value[1:])
    match = _FUNC_RE.match(value)
    if match:
        try:
            return _parse_function(match.group(1).lower(), match.group(2))
        except ValueError:
            return None
    return None
