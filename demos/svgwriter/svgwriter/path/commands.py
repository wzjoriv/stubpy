"""Path segment commands (M, L, H, V, C, S, Q, T, A, Z)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields, replace
from typing import ClassVar

from .._internal._constants import DEFAULT_PRECISION
from .._internal._speedups import format_number
from .._internal._typing import Self
from ..transform.matrix import Point

__all__ = [
    "ArcTo",
    "ClosePath",
    "CurveTo",
    "HLineTo",
    "LineTo",
    "MoveTo",
    "PathCommand",
    "QuadTo",
    "SmoothCurveTo",
    "SmoothQuadTo",
    "VLineTo",
]


class PathCommand(ABC):
    """One segment of path data."""

    code: ClassVar[str]
    coordinates: ClassVar[tuple[str, ...]] = ()
    relative: bool

    @property
    def letter(self) -> str:
        return self.code.lower() if self.relative else self.code

    @property
    @abstractmethod
    def arguments(self) -> tuple[float, ...]:
        """Numbers written after the command letter, in order."""

    @abstractmethod
    def end_point(self, current: Point, start: Point) -> Point:
        """Absolute pen position after this segment."""

    def to_absolute(self, current: Point) -> Self:
        """Return an absolute equivalent, given the current point."""
        if not self.relative:
            return self
        offsets = {
            name: getattr(self, name) + (current.x if name.startswith("x") else current.y)
            for name in self.coordinates
        }
        return replace(self, relative=False, **offsets)  # type: ignore[type-var]

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        args = " ".join(format_number(a, precision) for a in self.arguments)
        return f"{self.letter}{args}" if args else self.letter

    def __str__(self) -> str:
        return self.svg_value()


def _values(command: PathCommand) -> tuple[float, ...]:
    return tuple(
        float(getattr(command, f.name)) for f in fields(command)  # type: ignore[arg-type]
        if f.name != "relative"
    )


@dataclass(frozen=True)
class _XYCommand(PathCommand):
    """Shared behaviour for commands that end at ``(x, y)``."""

    def end_point(self, current: Point, start: Point) -> Point:
        x, y = getattr(self, "x"), getattr(self, "y")
        return Point(current.x + x, current.y + y) if self.relative else Point(x, y)

    @property
    def arguments(self) -> tuple[float, ...]:
        return _values(self)


@dataclass(frozen=True)
class MoveTo(_XYCommand):
    code: ClassVar[str] = "M"
    coordinates: ClassVar[tuple[str, ...]] = ("x", "y")
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class LineTo(_XYCommand):
    code: ClassVar[str] = "L"
    coordinates: ClassVar[tuple[str, ...]] = ("x", "y")
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class HLineTo(PathCommand):
    code: ClassVar[str] = "H"
    coordinates: ClassVar[tuple[str, ...]] = ("x",)
    x: float
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.x,)

    def end_point(self, current: Point, start: Point) -> Point:
        return Point(current.x + self.x if self.relative else self.x, current.y)


@dataclass(frozen=True)
class VLineTo(PathCommand):
    code: ClassVar[str] = "V"
    coordinates: ClassVar[tuple[str, ...]] = ("y",)
    y: float
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.y,)

    def end_point(self, current: Point, start: Point) -> Point:
        return Point(current.x, current.y + self.y if self.relative else self.y)


@dataclass(frozen=True)
class CurveTo(_XYCommand):
    """Cubic Bezier with two explicit control points."""

    code: ClassVar[str] = "C"
    coordinates: ClassVar[tuple[str, ...]] = ("x1", "y1", "x2", "y2", "x", "y")
    x1: float
    y1: float
    x2: float
    y2: float
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class SmoothCurveTo(_XYCommand):
    """Cubic Bezier whose first control point is reflected."""

    code: ClassVar[str] = "S"
    coordinates: ClassVar[tuple[str, ...]] = ("x2", "y2", "x", "y")
    x2: float
    y2: float
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class QuadTo(_XYCommand):
    code: ClassVar[str] = "Q"
    coordinates: ClassVar[tuple[str, ...]] = ("x1", "y1", "x", "y")
    x1: float
    y1: float
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class SmoothQuadTo(_XYCommand):
    code: ClassVar[str] = "T"
    coordinates: ClassVar[tuple[str, ...]] = ("x", "y")
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class ArcTo(_XYCommand):
    """Elliptical arc. Flags select one of the four candidate arcs."""

    code: ClassVar[str] = "A"
    coordinates: ClassVar[tuple[str, ...]] = ("x", "y")
    rx: float
    ry: float
    rotation: float
    large_arc: bool
    sweep: bool
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.rx, self.ry, self.rotation, int(self.large_arc), int(self.sweep), self.x, self.y)


@dataclass(frozen=True)
class ClosePath(PathCommand):
    code: ClassVar[str] = "Z"
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return ()

    def end_point(self, current: Point, start: Point) -> Point:
        return start
