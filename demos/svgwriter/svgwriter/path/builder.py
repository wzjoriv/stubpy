"""Fluent construction of path data."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

from .._internal._registry import chainable
from .._internal._typing import Self
from ..transform.matrix import Point
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
from .data import PathData

if TYPE_CHECKING:
    from ..elements.shapes import Path

__all__ = ["PathBuilder"]

FULL_CIRCLE: Final = 360.0
QUARTER_TURN: Final = 90.0


class PathBuilder:
    """Accumulate path commands with chained method calls.

    Every drawing method accepts ``relative=True`` to emit the lowercase
    form of the command.

    Examples
    --------
    >>> d = PathBuilder().move_to(0, 0).line_to(10, 0).arc_to(5, 5, 0, False, True, 10, 10).close()
    >>> str(d.build())
    'M0 0 L10 0 A5 5 0 0 1 10 10 Z'
    """

    __slots__ = ("_commands", "_current", "_start")

    def __init__(self, start: tuple[float, float] | None = None) -> None:
        self._commands: list[PathCommand] = []
        self._current = Point(0.0, 0.0)
        self._start = self._current
        if start is not None:
            self.move_to(*start)

    @property
    def current_point(self) -> Point:
        return self._current

    def _push(self, command: PathCommand) -> None:
        self._commands.append(command)
        self._current = command.end_point(self._current, self._start)
        if isinstance(command, MoveTo):
            self._start = self._current

    @chainable
    def move_to(self, x: float, y: float, *, relative: bool = False) -> None:
        self._push(MoveTo(x, y, relative=relative))

    @chainable
    def line_to(self, x: float, y: float, *, relative: bool = False) -> None:
        self._push(LineTo(x, y, relative=relative))

    @chainable
    def horizontal_to(self, x: float, *, relative: bool = False) -> None:
        self._push(HLineTo(x, relative=relative))

    @chainable
    def vertical_to(self, y: float, *, relative: bool = False) -> None:
        self._push(VLineTo(y, relative=relative))

    @chainable
    def curve_to(
        self, x1: float, y1: float, x2: float, y2: float, x: float, y: float, *, relative: bool = False
    ) -> None:
        self._push(CurveTo(x1, y1, x2, y2, x, y, relative=relative))

    @chainable
    def smooth_curve_to(self, x2: float, y2: float, x: float, y: float, *, relative: bool = False) -> None:
        self._push(SmoothCurveTo(x2, y2, x, y, relative=relative))

    @chainable
    def quad_to(self, x1: float, y1: float, x: float, y: float, *, relative: bool = False) -> None:
        self._push(QuadTo(x1, y1, x, y, relative=relative))

    @chainable
    def smooth_quad_to(self, x: float, y: float, *, relative: bool = False) -> None:
        self._push(SmoothQuadTo(x, y, relative=relative))

    @chainable
    def arc_to(
        self,
        rx: float,
        ry: float,
        rotation: float,
        large_arc: bool,
        sweep: bool,
        x: float,
        y: float,
        *,
        relative: bool = False,
    ) -> None:
        self._push(ArcTo(rx, ry, rotation, large_arc, sweep, x, y, relative=relative))

    @chainable
    def close(self) -> None:
        self._push(ClosePath())

    def extend(self, data: PathData | str) -> Self:
        for command in PathData(data) if isinstance(data, str) else data:
            self._push(command)
        return self

    def circle(self, cx: float, cy: float, r: float) -> Self:
        """Append a full circle as two half arcs."""
        self.move_to(cx - r, cy)
        self.arc_to(r, r, 0, False, True, cx + r, cy)
        self.arc_to(r, r, 0, False, True, cx - r, cy)
        return self.close()

    def regular_polygon(self, cx: float, cy: float, radius: float, sides: int, rotation: float = -QUARTER_TURN) -> Self:
        """Append a closed regular polygon; the first vertex points up by default."""
        if sides < 3:
            raise ValueError("a polygon needs at least three sides")
        for i in range(sides):
            angle = math.radians(rotation + FULL_CIRCLE * i / sides)
            x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
            if i == 0:
                self.move_to(x, y)
            else:
                self.line_to(x, y)
        return self.close()

    def build(self) -> PathData:
        return PathData(self._commands)

    def to_element(self, **kwargs: Any) -> Path:
        """Wrap the data in a ``<path>``; keywords go to ``Path``."""
        from ..elements.shapes import Path

        return Path(self.build(), **kwargs)

    def __len__(self) -> int:
        return len(self._commands)

    def __str__(self) -> str:
        return str(self.build())
