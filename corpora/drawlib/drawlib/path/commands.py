"""Path segment commands."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from typing import ClassVar

from ..attributes.values import DEFAULT_PRECISION, format_number
from ..transform import Point

__all__ = ["ClosePath", "CurveTo", "HLineTo", "LineTo", "MoveTo", "PathCommand"]


class PathCommand(ABC):
    """One segment of path data."""

    code: ClassVar[str]
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

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        args = " ".join(format_number(a, precision) for a in self.arguments)
        return f"{self.letter}{args}" if args else self.letter

    def __str__(self) -> str:
        return self.svg_value()


@dataclass(frozen=True)
class _XYCommand(PathCommand):
    """Shared behaviour for commands that end at ``(x, y)``."""

    def end_point(self, current: Point, start: Point) -> Point:
        x, y = getattr(self, "x"), getattr(self, "y")
        return Point(current.x + x, current.y + y) if self.relative else Point(x, y)

    @property
    def arguments(self) -> tuple[float, ...]:
        return tuple(float(getattr(self, f.name)) for f in fields(self) if f.name != "relative")  # type: ignore[arg-type]


@dataclass(frozen=True)
class MoveTo(_XYCommand):
    code: ClassVar[str] = "M"
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class LineTo(_XYCommand):
    code: ClassVar[str] = "L"
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class HLineTo(PathCommand):
    code: ClassVar[str] = "H"
    x: float
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return (self.x,)

    def end_point(self, current: Point, start: Point) -> Point:
        return Point(current.x + self.x if self.relative else self.x, current.y)


@dataclass(frozen=True)
class CurveTo(_XYCommand):
    """Cubic Bezier with two explicit control points."""

    code: ClassVar[str] = "C"
    x1: float
    y1: float
    x2: float
    y2: float
    x: float
    y: float
    relative: bool = field(default=False, kw_only=True)


@dataclass(frozen=True)
class ClosePath(PathCommand):
    code: ClassVar[str] = "Z"
    relative: bool = field(default=False, kw_only=True)

    @property
    def arguments(self) -> tuple[float, ...]:
        return ()

    def end_point(self, current: Point, start: Point) -> Point:
        return start
