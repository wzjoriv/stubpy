"""Path-data (``d`` attribute) parsing into absolute, normalized segments."""
from __future__ import annotations

from dataclasses import dataclass, field

COMMAND_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
_NUMBER_START = set("+-.0123456789")
_DIGITS = set("0123456789")
_ARC_FLAG_INDICES = (3, 4)


class PathSyntaxError(ValueError):
    """Raised for malformed path data."""


@dataclass
class Path:
    """Absolute segments: ``M L C Q A Z`` with their coordinates."""

    segments: list[tuple] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.segments)

    def move_to(self, x: float, y: float) -> Path:
        """Start a new subpath."""
        self.segments.append(("M", x, y))
        return self

    def line_to(self, x: float, y: float) -> Path:
        """Append a straight line."""
        self.segments.append(("L", x, y))
        return self

    def cubic_to(self, x1: float, y1: float, x2: float, y2: float, x: float, y: float) -> Path:
        """Append a cubic Bezier."""
        self.segments.append(("C", x1, y1, x2, y2, x, y))
        return self

    def quad_to(self, x1: float, y1: float, x: float, y: float) -> Path:
        """Append a quadratic Bezier."""
        self.segments.append(("Q", x1, y1, x, y))
        return self

    def arc_to(self, rx: float, ry: float, rotation: float, large: bool, sweep: bool,
               x: float, y: float) -> Path:
        """Append an elliptical arc."""
        self.segments.append(("A", rx, ry, rotation, bool(large), bool(sweep), x, y))
        return self

    def close(self) -> Path:
        """Close the current subpath."""
        self.segments.append(("Z",))
        return self


class _Scanner:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def skip_separators(self) -> None:
        while self.pos < len(self.text) and (self.text[self.pos].isspace() or self.text[self.pos] == ","):
            self.pos += 1

    def at_number(self) -> bool:
        self.skip_separators()
        return self.pos < len(self.text) and self.text[self.pos] in _NUMBER_START

    def flag(self) -> float:
        self.skip_separators()
        if self.pos < len(self.text) and self.text[self.pos] in "01":
            self.pos += 1
            return float(self.text[self.pos - 1])
        raise PathSyntaxError(f"expected arc flag at {self.pos}")

    def number(self) -> float:
        self.skip_separators()
        text, start = self.text, self.pos
        i = start
        if i < len(text) and text[i] in "+-":
            i += 1
        while i < len(text) and text[i] in _DIGITS:
            i += 1
        if i < len(text) and text[i] == ".":
            i += 1
            while i < len(text) and text[i] in _DIGITS:
                i += 1
        if i < len(text) and text[i] in "eE" and i + 1 < len(text) and (
                text[i + 1] in _DIGITS or (text[i + 1] in "+-" and i + 2 < len(text) and text[i + 2] in _DIGITS)):
            i += 2
            while i < len(text) and text[i] in _DIGITS:
                i += 1
        try:
            value = float(text[start:i])
        except ValueError:
            raise PathSyntaxError(f"bad number at {start}") from None
        self.pos = i
        return value

    def command(self) -> str | None:
        self.skip_separators()
        if self.pos >= len(self.text):
            return None
        ch = self.text[self.pos]
        if ch.upper() not in COMMAND_ARITY:
            raise PathSyntaxError(f"unexpected {ch!r} at {self.pos}")
        self.pos += 1
        return ch


def tokenize(d: str, strict: bool = True) -> list[tuple[str, list[float]]]:
    """Split path data into ``(command, args)`` pairs with implicit repeats expanded.

    With ``strict=False`` the pairs parsed before the first error are returned.
    """
    out: list[tuple[str, list[float]]] = []
    try:
        _tokenize_into(_Scanner(d or ""), out)
    except PathSyntaxError:
        if strict:
            raise
    return out


def _tokenize_into(scan: _Scanner, out: list) -> None:
    cmd = scan.command()
    if cmd is not None and cmd not in "Mm":
        raise PathSyntaxError("path data must start with a moveto")
    while cmd is not None:
        arity = COMMAND_ARITY[cmd.upper()]
        if arity == 0:
            out.append((cmd, []))
        else:
            first = True
            while first or scan.at_number():
                args = [scan.flag() if cmd in "Aa" and i in _ARC_FLAG_INDICES else scan.number()
                        for i in range(arity)]
                out.append((cmd, args))
                if cmd in "Mm":
                    cmd = "l" if cmd == "m" else "L"
                first = False
        cmd = scan.command()


def _reflect(prev: tuple | None, kind: str, x: float, y: float) -> tuple[float, float]:
    if prev is not None and prev[0] == kind:
        cx, cy = prev[-4], prev[-3]
        return 2 * x - cx, 2 * y - cy
    return x, y


def parse_path(d: str, strict: bool = False) -> Path:
    """Parse path data; on errors keep what parsed so far unless ``strict``."""
    path = Path()
    tokens = tokenize(d, strict)
    x = y = start_x = start_y = 0.0
    prev: tuple | None = None
    for cmd, args in tokens:
        rel = cmd.islower()
        up = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            x, y = args[0] + ox, args[1] + oy
            start_x, start_y = x, y
            seg = ("M", x, y)
        elif up == "L":
            x, y = args[0] + ox, args[1] + oy
            seg = ("L", x, y)
        elif up == "H":
            x = args[0] + ox
            seg = ("L", x, y)
        elif up == "V":
            y = args[0] + oy
            seg = ("L", x, y)
        elif up == "C":
            seg = ("C", args[0] + ox, args[1] + oy, args[2] + ox, args[3] + oy, args[4] + ox, args[5] + oy)
            x, y = seg[5], seg[6]
        elif up == "S":
            x1, y1 = _reflect(prev, "C", x, y)
            seg = ("C", x1, y1, args[0] + ox, args[1] + oy, args[2] + ox, args[3] + oy)
            x, y = seg[5], seg[6]
        elif up == "Q":
            seg = ("Q", args[0] + ox, args[1] + oy, args[2] + ox, args[3] + oy)
            x, y = seg[3], seg[4]
        elif up == "T":
            x1, y1 = _reflect(prev, "Q", x, y)
            seg = ("Q", x1, y1, args[0] + ox, args[1] + oy)
            x, y = seg[3], seg[4]
        elif up == "A":
            seg = ("A", abs(args[0]), abs(args[1]), args[2], bool(args[3]), bool(args[4]),
                   args[5] + ox, args[6] + oy)
            x, y = seg[6], seg[7]
        else:
            seg = ("Z",)
            x, y = start_x, start_y
        path.segments.append(seg)
        prev = seg
    return path
