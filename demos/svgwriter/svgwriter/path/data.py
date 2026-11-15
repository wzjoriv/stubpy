"""Immutable path data with normalization and bounding boxes."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from functools import cached_property
from typing import Final, NamedTuple, overload

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number
from ..transform.matrix import Matrix, Point
from ..transform.transform import TransformLike, as_transform
from ._affine import transform_commands
from .arc import endpoint_to_center
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
from .parser import parse_path

__all__ = ["BBox", "PathData", "PathDataLike"]

CURVE_SAMPLES: Final = 16
ARC_SAMPLES: Final = 32
ORIGIN: Final = Point(0.0, 0.0)
_IMPLIED: Final = {"M": "L", "m": "l"}


def _short_number(text: str) -> str:
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


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

    def union(self, other: BBox) -> BBox:
        return BBox.from_points(
            [(self.x, self.y), (self.x + self.width, self.y + self.height),
             (other.x, other.y), (other.x + other.width, other.y + other.height)]
        )


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return Point(
        u**3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t**3 * p3.x,
        u**3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t**3 * p3.y,
    )


def _quadratic(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    u = 1.0 - t
    return Point(
        u * u * p0.x + 2 * u * t * p1.x + t * t * p2.x,
        u * u * p0.y + 2 * u * t * p1.y + t * t * p2.y,
    )


def _reflect(control: Point, about: Point) -> Point:
    return Point(2 * about.x - control.x, 2 * about.y - control.y)


class PathData(Sequence[PathCommand]):
    """A parsed, immutable sequence of path commands.

    Parameters
    ----------
    commands : str or iterable of PathCommand
        Path data text or commands.

    Examples
    --------
    >>> d = PathData("M0 0 h10 v10 z")
    >>> str(d.to_absolute())
    'M0 0 H10 V10 Z'
    >>> d.bbox
    BBox(x=0.0, y=0.0, width=10.0, height=10.0)
    >>> str(d * Matrix.translate(5, 0))
    'M5 0 L15 0 L15 10 Z'
    >>> len((d + "M20 20 h5").subpaths())
    2
    """

    def __init__(self, commands: str | Iterable[PathCommand] = ()) -> None:
        if isinstance(commands, str):
            self._commands: tuple[PathCommand, ...] = tuple(parse_path(commands))
        else:
            self._commands = tuple(commands)

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

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PathData) and self._commands == other._commands

    def __hash__(self) -> int:
        return hash(self._commands)

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

    def transformed(self, transform: TransformLike) -> PathData:
        """Bake *transform* into the coordinates; arcs stay arcs."""
        matrix = transform if isinstance(transform, Matrix) else as_transform(transform).to_matrix()
        return PathData(transform_commands(self.normalized(), matrix))

    def subpaths(self) -> list[PathData]:
        """Split at each ``moveto``; every piece is absolute."""
        pieces: list[list[PathCommand]] = []
        for _, command in self.walk():
            if isinstance(command, MoveTo) or not pieces:
                pieces.append([])
            pieces[-1].append(command)
        return [PathData(piece) for piece in pieces]

    def __repr__(self) -> str:
        return f"PathData({str(self)!r})"

    def walk(self) -> Iterator[tuple[Point, PathCommand]]:
        """Yield ``(current_point, absolute_command)`` pairs."""
        current = start = ORIGIN
        for command in self._commands:
            absolute = command.to_absolute(current)
            yield current, absolute
            current = absolute.end_point(current, start)
            if isinstance(absolute, MoveTo):
                start = current
            elif isinstance(absolute, ClosePath):
                current = start

    def to_absolute(self) -> PathData:
        return PathData(command for _, command in self.walk())

    def normalized(self) -> PathData:
        """Absolute commands using only M, L, C, Q, A and Z."""
        result: list[PathCommand] = []
        previous: PathCommand | None = None
        last_control: Point | None = None
        for current, command in self.walk():
            if isinstance(command, HLineTo):
                command = LineTo(command.x, current.y)
            elif isinstance(command, VLineTo):
                command = LineTo(current.x, command.y)
            elif isinstance(command, SmoothCurveTo):
                c1 = _reflect(last_control, current) if isinstance(previous, CurveTo) and last_control else current
                command = CurveTo(c1.x, c1.y, command.x2, command.y2, command.x, command.y)
            elif isinstance(command, SmoothQuadTo):
                c1 = _reflect(last_control, current) if isinstance(previous, QuadTo) and last_control else current
                command = QuadTo(c1.x, c1.y, command.x, command.y)
            if isinstance(command, CurveTo):
                last_control = Point(command.x2, command.y2)
            elif isinstance(command, QuadTo):
                last_control = Point(command.x1, command.y1)
            else:
                last_control = None
            result.append(command)
            previous = command
        return PathData(result)

    def points(self) -> Iterator[Point]:
        """Yield points sampled along the path's outline."""
        current = ORIGIN
        for command in self.normalized():
            if isinstance(command, (MoveTo, LineTo)):
                yield Point(command.x, command.y)
            elif isinstance(command, CurveTo):
                c1, c2, end = Point(command.x1, command.y1), Point(command.x2, command.y2), Point(command.x, command.y)
                for i in range(1, CURVE_SAMPLES + 1):
                    yield _cubic(current, c1, c2, end, i / CURVE_SAMPLES)
            elif isinstance(command, QuadTo):
                c1, end = Point(command.x1, command.y1), Point(command.x, command.y)
                for i in range(1, CURVE_SAMPLES + 1):
                    yield _quadratic(current, c1, end, i / CURVE_SAMPLES)
            elif isinstance(command, ArcTo):
                end = Point(command.x, command.y)
                arc = endpoint_to_center(current, end, command.rx, command.ry, command.rotation, command.large_arc, command.sweep)
                yield from (arc.sample(ARC_SAMPLES) if arc else [end])
            if not isinstance(command, ClosePath):
                current = Point(command.x, command.y)  # type: ignore[attr-defined]

    @cached_property
    def bbox(self) -> BBox | None:
        """Approximate bounding box, or ``None`` for empty data."""
        points = list(self.points())
        return BBox.from_points(points) if points else None

    def svg_value(self, precision: int = DEFAULT_PRECISION, *, compact: bool = False) -> str:
        """Serialize; ``compact`` drops repeated letters and spaces."""
        if not compact:
            return " ".join(command.svg_value(precision) for command in self._commands)
        out: list[str] = []
        previous = ""
        for command in self._commands:
            letter = command.letter
            needs_separator = letter == _IMPLIED.get(previous, previous) and letter not in "Zz"
            if not needs_separator:
                out.append(letter)
            for value in command.arguments:
                text = _short_number(format_number(value, precision))
                if needs_separator and not text.startswith("-"):
                    out.append(" ")
                out.append(text)
                needs_separator = True
            previous = letter
        return "".join(out)

    def __str__(self) -> str:
        return self.svg_value()


PathDataLike = PathData | str | Iterable[PathCommand]
