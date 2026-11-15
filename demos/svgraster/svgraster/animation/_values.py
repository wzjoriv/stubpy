"""Animation values: parsing, addition, distance, formatting and calcMode interpolation."""
from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass

from ..dom.color import parse_color

_NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
COLOR_ATTRIBUTES = frozenset({"fill", "stroke", "stop-color", "flood-color", "lighting-color", "color"})
SPLINE_ITERATIONS = 24
BYTE_MAX = 255.0


@dataclass(frozen=True)
class Value:
    """A string split into fixed text and interpolable numbers, or a color."""

    text: str
    parts: tuple[str, ...] = ()
    numbers: tuple[float, ...] = ()
    color: tuple[float, float, float, float] | None = None

    @property
    def numeric(self) -> bool:
        """Whether the value has numbers or is a color."""
        return self.color is not None or bool(self.numbers)

    def compatible(self, other: Value) -> bool:
        """Whether the two values can be interpolated."""
        if self.color is not None or other.color is not None:
            return self.color is not None and other.color is not None
        return self.parts == other.parts and len(self.numbers) == len(other.numbers) and bool(self.numbers)


def parse_value(text: str, attribute: str = "") -> Value:
    """Split ``text`` into interpolable pieces; colors are recognised for color attributes."""
    text = text.strip()
    if attribute in COLOR_ATTRIBUTES or text.startswith(("#", "rgb", "hsl")):
        color = parse_color(text)
        if color is not None and not text.startswith("url("):
            return Value(text, color=(color.r, color.g, color.b, color.a))
        if attribute in COLOR_ATTRIBUTES:
            return Value(text)
    parts, numbers, last = [], [], 0
    for match in _NUMBER_RE.finditer(text):
        parts.append(text[last:match.start()])
        numbers.append(float(match.group(0)))
        last = match.end()
    parts.append(text[last:])
    return Value(text, tuple(parts), tuple(numbers))


def format_number(v: float) -> str:
    """A compact decimal for SVG output."""
    out = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if out in ("-0", "") else out


def format_value(v: Value) -> str:
    """The SVG text of ``v``."""
    if v.color is not None:
        r, g, b, a = (min(1.0, max(0.0, c)) for c in v.color)
        rgb = ", ".join(str(int(round(c * BYTE_MAX))) for c in (r, g, b))
        return f"rgb({rgb})" if a >= 1.0 else f"rgba({rgb}, {format_number(a)})"
    if not v.numbers:
        return v.text
    out = [v.parts[0]]
    for n, part in zip(v.numbers, v.parts[1:]):
        out += [format_number(n), part]
    return "".join(out)


def _combine(a: Value, b: Value, fa: float, fb: float) -> Value:
    if a.color is not None and b.color is not None:
        rgb = tuple(fa * x + fb * y for x, y in zip(a.color[:3], b.color[:3]))
        alpha = fa * a.color[3] + fb * b.color[3] if (fa + fb) == 1.0 else max(a.color[3], b.color[3])
        return Value("", color=rgb + (alpha,))
    return Value("", a.parts, tuple(fa * x + fb * y for x, y in zip(a.numbers, b.numbers)))


def lerp(a: Value, b: Value, f: float) -> Value:
    """Linear interpolation, or ``a`` until ``f`` reaches 0.5 then ``b`` when incompatible."""
    if not a.compatible(b):
        return a if f < 0.5 else b
    return _combine(a, b, 1.0 - f, f)


def add(a: Value, b: Value, times: float = 1.0) -> Value:
    """``a + times * b`` for compatible values; ``b`` otherwise."""
    if not a.compatible(b):
        return b
    return _combine(a, b, 1.0, times)


def distance(a: Value, b: Value) -> float:
    """Euclidean distance used by ``calcMode="paced"``."""
    if not a.compatible(b):
        return 0.0
    if a.color is not None:
        return math.dist([c * BYTE_MAX for c in a.color[:3]], [c * BYTE_MAX for c in b.color[:3]])
    return math.dist(a.numbers, b.numbers)


def bezier_ease(spline: tuple[float, float, float, float], x: float) -> float:
    """Evaluate a ``keySplines`` cubic timing curve at progress ``x``."""
    x1, y1, x2, y2 = spline

    def coord(t: float, p1: float, p2: float) -> float:
        mt = 1.0 - t
        return 3 * mt * mt * t * p1 + 3 * mt * t * t * p2 + t * t * t

    lo, hi = 0.0, 1.0
    for _ in range(SPLINE_ITERATIONS):
        mid = (lo + hi) / 2.0
        if coord(mid, x1, x2) < x:
            lo = mid
        else:
            hi = mid
    return coord((lo + hi) / 2.0, y1, y2)


def parse_splines(text: str | None) -> list[tuple[float, float, float, float]]:
    """``keySplines`` as a list of four-number tuples."""
    out = []
    for chunk in (text or "").split(";"):
        nums = [float(n) for n in _NUMBER_RE.findall(chunk)]
        if len(nums) == 4:
            out.append(tuple(nums))
    return out


def parse_key_times(text: str | None) -> list[float]:
    """``keyTimes`` (or ``keyPoints``) as floats."""
    return [float(n) for n in _NUMBER_RE.findall(text or "")]


def segment_at(key_times: list[float], p: float) -> tuple[int, float]:
    """The segment index and local progress for overall progress ``p``."""
    n = len(key_times)
    i = min(max(bisect.bisect_right(key_times, p) - 1, 0), n - 2)
    span = key_times[i + 1] - key_times[i]
    return i, (0.0 if span <= 0 else min(1.0, max(0.0, (p - key_times[i]) / span)))


def interpolate(values: list[Value], p: float, mode: str = "linear", key_times: list[float] | None = None,
                splines: list | None = None) -> Value:
    """The value at progress ``p`` in ``[0, 1]`` of the simple duration."""
    n = len(values)
    if n == 1:
        return values[0]
    if mode == "discrete":
        if key_times and len(key_times) == n:
            return values[max(0, bisect.bisect_right(key_times, p) - 1)]
        return values[min(int(p * n), n - 1)]
    if mode == "paced":
        dists = [distance(values[i], values[i + 1]) for i in range(n - 1)]
        total = sum(dists)
        if total > 0:
            acc, key_times = 0.0, [0.0]
            for d in dists:
                acc += d
                key_times.append(acc / total)
        else:
            key_times = None
    if not key_times or len(key_times) != n:
        key_times = [i / (n - 1) for i in range(n)]
    if p >= 1.0:
        return values[-1]
    i, local = segment_at(key_times, p)
    if mode == "spline" and splines and i < len(splines):
        local = bezier_ease(splines[i], local)
    return lerp(values[i], values[i + 1], local)


def zero_like(v: Value) -> Value:
    """A value of the same shape with every number zero (the base of a ``by`` animation)."""
    if v.color is not None:
        return Value("", color=(0.0, 0.0, 0.0, v.color[3]))
    return Value("", v.parts, tuple(0.0 for _ in v.numbers))

