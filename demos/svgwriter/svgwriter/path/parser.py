"""Tokenizer and parser for path data (the ``d`` attribute)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

from .commands import (
    ArcTo,
    ClosePath,
    CurveTo,
    HLineTo,
    LineTo,
    MoveTo,
    PathCommand,
    QuadTo,
    SmoothCurveTo,
    SmoothQuadTo,
    VLineTo,
)

__all__ = ["PathSyntaxError", "iter_commands", "parse_path"]

_NUMBER_RE: Final = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_SEPARATORS: Final = " \t\r\n,"
_COMMANDS: Final[dict[str, type[PathCommand]]] = {
    "M": MoveTo,
    "L": LineTo,
    "H": HLineTo,
    "V": VLineTo,
    "C": CurveTo,
    "S": SmoothCurveTo,
    "Q": QuadTo,
    "T": SmoothQuadTo,
    "A": ArcTo,
    "Z": ClosePath,
}
_ARITY: Final = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
_ARC_FLAG_POSITIONS: Final = (3, 4)


class PathSyntaxError(ValueError):
    """Raised for malformed path data."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} at offset {position}")
        self.position = position


class _Scanner:
    __slots__ = ("pos", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def skip(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] in _SEPARATORS:
            self.pos += 1

    def at_end(self) -> bool:
        self.skip()
        return self.pos >= len(self.text)

    def peek_command(self) -> str | None:
        self.skip()
        if self.pos < len(self.text) and self.text[self.pos].upper() in _COMMANDS:
            return self.text[self.pos]
        return None

    def number(self) -> float:
        self.skip()
        match = _NUMBER_RE.match(self.text, self.pos)
        if match is None:
            raise PathSyntaxError("expected a number", self.pos)
        self.pos = match.end()
        return float(match.group())

    def flag(self) -> bool:
        self.skip()
        if self.pos >= len(self.text) or self.text[self.pos] not in "01":
            raise PathSyntaxError("expected an arc flag", self.pos)
        self.pos += 1
        return self.text[self.pos - 1] == "1"


def _arguments(scanner: _Scanner, code: str) -> list[float]:
    args: list[float] = []
    for index in range(_ARITY[code]):
        if code == "A" and index in _ARC_FLAG_POSITIONS:
            args.append(float(scanner.flag()))
        else:
            args.append(scanner.number())
    return args


def _build(code: str, relative: bool, args: list[float]) -> PathCommand:
    cls = _COMMANDS[code]
    if code == "A":
        rx, ry, rotation, large, sweep, x, y = args
        return ArcTo(rx, ry, rotation, bool(large), bool(sweep), x, y, relative=relative)
    return cls(*args, relative=relative)  # type: ignore[call-arg]


def iter_commands(text: str) -> Iterator[PathCommand]:
    """Yield commands from path data, expanding implicit repeats."""
    scanner = _Scanner(text)
    if scanner.at_end():
        return
    letter = scanner.peek_command()
    if letter is None or letter.upper() != "M":
        raise PathSyntaxError("path data must start with a moveto", scanner.pos)
    while not scanner.at_end():
        letter = scanner.peek_command()
        if letter is None:
            raise PathSyntaxError("expected a command", scanner.pos)
        scanner.pos += 1
        code, relative = letter.upper(), letter.islower()
        if code == "Z":
            yield ClosePath(relative=relative)
            continue
        yield _build(code, relative, _arguments(scanner, code))
        if code == "M":
            code = "L"
        while not scanner.at_end() and scanner.peek_command() is None:
            yield _build(code, relative, _arguments(scanner, code))


def parse_path(text: str) -> list[PathCommand]:
    """Parse path data into a list of commands."""
    return list(iter_commands(text))
