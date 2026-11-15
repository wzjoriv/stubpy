"""CSS/SVG length parsing and unit conversion."""
from __future__ import annotations

import re
from dataclasses import dataclass

CSS_DPI = 96.0
POINTS_PER_INCH = 72.0
PICAS_PER_INCH = 6.0
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54
EX_PER_EM = 0.5
DEFAULT_FONT_SIZE = 16.0
PERCENT = 100.0

_LENGTH_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)\s*$")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


@dataclass(frozen=True)
class UnitContext:
    """What relative units resolve against."""

    font_size: float = DEFAULT_FONT_SIZE
    viewport_width: float = 0.0
    viewport_height: float = 0.0

    @property
    def viewport_diagonal(self) -> float:
        """The normalized diagonal used for percentages of non-axis lengths."""
        return ((self.viewport_width ** 2 + self.viewport_height ** 2) / 2.0) ** 0.5


def _unit_scale(unit: str, ctx: UnitContext) -> float:
    scales = {
        "": 1.0, "px": 1.0,
        "in": CSS_DPI,
        "pt": CSS_DPI / POINTS_PER_INCH,
        "pc": CSS_DPI / PICAS_PER_INCH,
        "mm": CSS_DPI / MM_PER_INCH,
        "cm": CSS_DPI / CM_PER_INCH,
        "em": ctx.font_size,
        "ex": ctx.font_size * EX_PER_EM,
    }
    if unit not in scales:
        raise ValueError(f"unknown unit {unit!r}")
    return scales[unit]


def split_length(text: str) -> tuple[float, str]:
    """Split ``"12.5mm"`` into ``(12.5, "mm")``."""
    match = _LENGTH_RE.match(text)
    if not match:
        raise ValueError(f"invalid length {text!r}")
    return float(match.group(1)), match.group(2).lower()


def parse_length(text: str | None, ctx: UnitContext = UnitContext(), axis: str = "x",
                 default: float = 0.0) -> float:
    """Resolve a length to user units; ``axis`` picks the percentage base."""
    if text is None or not str(text).strip():
        return default
    try:
        value, unit = split_length(str(text))
    except ValueError:
        return default
    if unit == "%":
        base = {"x": ctx.viewport_width, "y": ctx.viewport_height}.get(axis, ctx.viewport_diagonal)
        return value * base / PERCENT
    try:
        return value * _unit_scale(unit, ctx)
    except ValueError:
        return default


def parse_fraction(text: str | None, default: float = 0.0) -> float:
    """Parse a number or percentage as a fraction (``"50%"`` -> 0.5)."""
    if text is None or not str(text).strip():
        return default
    text = str(text).strip()
    try:
        if text.endswith("%"):
            return float(text[:-1]) / PERCENT
        return float(text)
    except ValueError:
        return default


def parse_numbers(text: str | None) -> list[float]:
    """Parse a whitespace/comma separated list of numbers."""
    if not text:
        return []
    return [float(tok) for tok in _NUMBER_RE.findall(str(text))]


def parse_length_list(text: str | None, ctx: UnitContext = UnitContext(), axis: str = "xy") -> list[float]:
    """Parse a list of lengths such as a dash array."""
    if not text or text.strip() == "none":
        return []
    tokens = [t for t in re.split(r"[\s,]+", text.strip()) if t]
    return [parse_length(t, ctx, axis) for t in tokens]
