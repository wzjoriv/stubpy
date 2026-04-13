# demo/style.py  —  PixelForge / style resolution
# -------------------------------------------------------
# Exercises: @overload on module functions, @overload on instance and class
#            methods, mixed sync + async overloads, three+ variant overloads.
#            Every overload group has a suppressed concrete implementation.
"""
Colour and style resolution for PixelForge.

The functions and classes here demonstrate how one paint / style system
works when you want typed dispatch on different input forms:

  - parse_color("ff0000") → Color
  - parse_color((1.0, 0.0, 0.0)) → Color
  - parse_color(0xFF0000) → Color
"""
from __future__ import annotations

from typing import Generic, TypeVar, overload

from demo import types

__all__ = [
    "parse_color",
    "blend",
    "lerp",
    "Brush",
    "GradientStop",
]

T = TypeVar("T", int, float)


# ── Three-variant @overload: string, int, tuple ───────────────────────────

@overload
def parse_color(value: str) -> types.Color: ...
@overload
def parse_color(value: int) -> types.Color: ...
@overload
def parse_color(value: tuple[float, float, float]) -> types.Color: ...
@overload
def parse_color(value: tuple[float, float, float, float]) -> types.Color: ...
def parse_color(value):
    """Parse *value* into a normalised RGBA :data:`~demo.types.Color` tuple.

    Accepts:

    - ``str`` — CSS hex string ``"#rgb"`` or ``"#rrggbb"`` (with or without ``#``).
    - ``int`` — packed 0xRRGGBB integer (e.g. ``0xFF8800``).
    - ``tuple[float, float, float]`` — RGB triple, alpha defaults to 1.0.
    - ``tuple[float, float, float, float]`` — RGBA quadruple.
    """
    if isinstance(value, str):
        h = value.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        return (r, g, b, 1.0)
    if isinstance(value, int):
        r = ((value >> 16) & 0xFF) / 255
        g = ((value >> 8)  & 0xFF) / 255
        b = (value & 0xFF) / 255
        return (r, g, b, 1.0)
    if len(value) == 3:
        return (*value, 1.0)
    return value


# ── Two-variant @overload: weighted vs equal blend ────────────────────────

@overload
def blend(a: types.Color, b: types.Color, t: float) -> types.Color: ...
@overload
def blend(a: types.Color, b: types.Color) -> types.Color: ...
def blend(a, b, t=0.5):
    """Linearly interpolate two colours.  *t* = 0.5 gives an equal mix."""
    return tuple(av + (bv - av) * t for av, bv in zip(a, b))


# ── Generic @overload preserving numeric type ─────────────────────────────

@overload
def lerp(a: int, b: int, t: float) -> int: ...
@overload
def lerp(a: float, b: float, t: float) -> float: ...
def lerp(a, b, t):
    """Interpolate between two numeric values, preserving the input type."""
    result = a + (b - a) * t
    return type(a)(result)


# ── Class with overloaded factory classmethod and overloaded instance method

class Brush(Generic[T]):
    """A parametric brush whose stroke width is typed over *T* (int or float).

    Demonstrates overloads on both classmethods and instance methods.
    """

    def __init__(self, width: T, color: types.Color = (0.0, 0.0, 0.0, 1.0)) -> None:
        self.width = width
        self.color = color

    @classmethod
    @overload
    def from_css(cls, spec: str) -> "Brush[float]": ...
    @classmethod
    @overload
    def from_css(cls, spec: str, *, integer_width: bool) -> "Brush[int]": ...
    @classmethod
    def from_css(cls, spec, **kwargs):
        """Create a Brush by parsing a CSS shorthand string."""
        width: float = float(spec.split()[0].rstrip("px"))
        if kwargs.get("integer_width"):
            return cls(int(width))
        return cls(width)

    @overload
    def scale(self, factor: int) -> "Brush[int]": ...
    @overload
    def scale(self, factor: float) -> "Brush[float]": ...
    def scale(self, factor):
        """Return a new Brush with width multiplied by *factor*."""
        return Brush(type(self.width)(self.width * factor), self.color)


# ── NamedTuple used as a typed gradient stop ──────────────────────────────

from typing import NamedTuple


class GradientStop(NamedTuple):
    """An immutable colour stop in a linear or radial gradient."""

    position: float          # 0.0 – 1.0 along the gradient axis
    color:    types.Color    # RGBA colour at this stop
    hint:     float = 0.5   # colour-hint (midpoint between this and next stop)
