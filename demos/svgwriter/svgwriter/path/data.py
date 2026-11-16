"""Immutable path data, its parser and a builder."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from functools import cached_property
from typing import NamedTuple, TypeAlias, overload

from .._internal._helpers import chainable
from ..attributes.values import DEFAULT_PRECISION
from ..transform import Matrix, Point, TransformLike, as_transform
from .commands import ClosePath, CurveTo, HLineTo, LineTo, MoveTo, PathCommand

__all__ = ["BBox", "PathBuilder", "PathData", "PathDataLike", "parse_path"]

_TOKEN_RE = re.compile(r"[MmLlHhCcZz]|[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_ARITY = {"M": 2, "L": 2, "H": 1, "C": 6, "Z": 0}
_CLASSES: dict[str, type[PathCommand]] = {"M": MoveTo, "L": LineTo, "H": HLineTo, "C": CurveTo, "Z": ClosePath}


class BBox(NamedTuple):
    """Axis-aligned bounding box."""

    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_points(cls, points: Iterable[Point | tuple[float, float]]) -> BBox:
        xs, ys = zip(*points)
        return cls(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2.0, self.y + self.height / 2.0)


def parse_path(text: str) -> list[PathCommand]:
    """Parse path data text into commands."""
    tokens = _TOKEN_RE.findall(text)
    commands: list[PathCommand] = []
    letter, index = "", 0
    while index < len(tokens):
        if tokens[index].isalpha():
            letter, index = tokens[index], index + 1
        key = letter.upper()
        count = _ARITY[key]
        numbers = [float(t) for t in tokens[index : index + count]]
        index += count
        commands.append(_CLASSES[key](*numbers, relative=letter.islower()))  # type: ignore[arg-type]
        if key == "M":
            letter = "l" if letter == "m" else "L"
    return commands


class PathData(Sequence[PathCommand]):
    """A parsed, immutable sequence of path commands.

    >>> str(PathData("M0 0 h10 z").to_absolute())
    'M0 0 H10 Z'
    """

    def __init__(self, commands: str | Iterable[PathCommand] = ()) -> None:
        self._commands: tuple[PathCommand, ...] = tuple(parse_path(commands) if isinstance(commands, str) else commands)

    @overload
    def __getitem__(self, index: int) -> PathCommand: ...
    @overload
    def __getitem__(self, index: slice) -> PathData: ...
    def __getitem__(self, index: int | slice) -> PathCommand | PathData:
        if isinstance(index, slice):
            return PathData(self._commands[index])
        return self._commands[index]

    def __len__(self) -> int:
        return len(self._commands)

    def __iter__(self) -> Iterator[PathCommand]:
        return iter(self._commands)

    def __add__(self, other: PathData | str) -> PathData:
        if isinstance(other, str):
            other = PathData(other)
        if not isinstance(other, PathData):
            return NotImplemented
        return PathData(self._commands + other._commands)

    def __radd__(self, other: PathData | str | int) -> PathData:
        if isinstance(other, int) and other == 0:
            return self
        if isinstance(other, str):
            return PathData(other) + self
        return NotImplemented

    def __mul__(self, transform: TransformLike) -> PathData:
        if not isinstance(transform, (str, Matrix)) and not hasattr(transform, "to_matrix"):
            return NotImplemented
        return self.transformed(transform)

    def __matmul__(self, transform: TransformLike) -> PathData:
        return self.__mul__(transform)

    def __rmatmul__(self, transform: TransformLike) -> PathData:
        return self.__mul__(transform)

    def walk(self) -> Iterator[tuple[Point, PathCommand]]:
        """Yield ``(current_point, command)`` pairs."""
        current = start = Point(0.0, 0.0)
        for command in self._commands:
            yield current, command
            current = command.end_point(current, start)
            if isinstance(command, MoveTo):
                start = current

    def to_absolute(self) -> PathData:
        result: list[PathCommand] = []
        for current, command in self.walk():
            if isinstance(command, HLineTo) and command.relative:
                command = HLineTo(current.x + command.x)
            elif isinstance(command, (MoveTo, LineTo)) and command.relative:
                command = type(command)(current.x + command.x, current.y + command.y)
            result.append(command)
        return PathData(result)

    def transformed(self, transform: TransformLike) -> PathData:
        """Bake *transform* into the coordinates; every segment becomes absolute."""
        matrix = transform if isinstance(transform, Matrix) else as_transform(transform).to_matrix()
        result: list[PathCommand] = []
        for current, command in self.to_absolute().walk():
            if isinstance(command, HLineTo):
                command = LineTo(command.x, current.y)
            if isinstance(command, (MoveTo, LineTo)):
                result.append(type(command)(*matrix.apply(command.x, command.y)))
            elif isinstance(command, CurveTo):
                points = [matrix.apply(*p) for p in ((command.x1, command.y1), (command.x2, command.y2), (command.x, command.y))]
                result.append(CurveTo(*(v for p in points for v in p)))
            else:
                result.append(command)
        return PathData(result)

    @cached_property
    def bbox(self) -> BBox | None:
        points = [Point(c.x, c.y) for c in self.to_absolute() if isinstance(c, (MoveTo, LineTo))]
        return BBox.from_points(points) if points else None

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return " ".join(c.svg_value(precision) for c in self._commands)

    def __str__(self) -> str:
        return self.svg_value()

    def __repr__(self) -> str:
        return f"PathData({str(self)!r})"


PathDataLike: TypeAlias = "PathData | str | Iterable[PathCommand]"


class PathBuilder:
    """Fluent construction of path data."""

    def __init__(self) -> None:
        self._commands: list[PathCommand] = []

    @chainable
    def move_to(self, x: float, y: float) -> None:
        self._commands.append(MoveTo(x, y))

    @chainable
    def line_to(self, x: float, y: float) -> None:
        self._commands.append(LineTo(x, y))

    @chainable
    def curve_to(self, x1: float, y1: float, x2: float, y2: float, x: float, y: float) -> None:
        self._commands.append(CurveTo(x1, y1, x2, y2, x, y))

    @chainable
    def close(self) -> None:
        self._commands.append(ClosePath())

    def build(self) -> PathData:
        return PathData(self._commands)
