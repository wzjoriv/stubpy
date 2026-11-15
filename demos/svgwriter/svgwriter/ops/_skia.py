"""Loading skia-python and converting paths to and from it."""

from __future__ import annotations

import importlib
from functools import cache
from typing import TYPE_CHECKING, Any, Final, TypeAlias, Union

from ..path.commands import ArcTo, ClosePath, CurveTo, LineTo, MoveTo, QuadTo
from ..path.data import PathData

if TYPE_CHECKING:
    from ..elements._geometry import PathOperand

__all__ = [
    "INSTALL_HINT",
    "Geometry",
    "MissingDependencyError",
    "available",
    "from_skia",
    "geometry_data",
    "require_skia",
    "to_skia",
]

INSTALL_HINT: Final = "pip install 'svgwriter[ops]'  (or: pip install skia-python)"
CONIC_SUBDIVISION: Final = 3
EVENODD: Final = "evenodd"

Geometry: TypeAlias = Union["PathOperand", PathData, str]
"""Anything with an outline: a shape, text, path data or ``d`` text."""


class MissingDependencyError(ImportError):
    """An optional dependency needed by the called feature is not installed."""


@cache
def _load() -> Any:
    try:
        return importlib.import_module("skia")
    except ImportError:
        return None


def available() -> bool:
    """Whether skia-python is importable."""
    return _load() is not None


def require_skia(feature: str) -> Any:
    """Return the ``skia`` module or raise :class:`MissingDependencyError`."""
    skia = _load()
    if skia is None:
        raise MissingDependencyError(f"{feature} needs skia-python, which is not installed. Install it with: {INSTALL_HINT}")
    return skia


def geometry_data(item: Geometry) -> tuple[PathData, bool]:
    """Path data in user units plus whether it fills even-odd."""
    from ..elements._geometry import PathOperand

    if isinstance(item, PathOperand):
        return item.outline(), str(item.get("fill-rule", "")) == EVENODD
    if isinstance(item, PathData):
        return item, False
    if isinstance(item, str):
        return PathData(item), False
    raise TypeError(f"expected a shape, text, PathData or path text, got {type(item).__name__}")


def to_skia(data: PathData, *, evenodd: bool = False) -> Any:
    """Build a ``skia.Path`` from path data."""
    skia = require_skia("path conversion")
    path = skia.Path()
    for command in data.normalized():
        if isinstance(command, MoveTo):
            path.moveTo(command.x, command.y)
        elif isinstance(command, LineTo):
            path.lineTo(command.x, command.y)
        elif isinstance(command, CurveTo):
            path.cubicTo(command.x1, command.y1, command.x2, command.y2, command.x, command.y)
        elif isinstance(command, QuadTo):
            path.quadTo(command.x1, command.y1, command.x, command.y)
        elif isinstance(command, ArcTo):
            size = skia.Path.ArcSize.kLarge_ArcSize if command.large_arc else skia.Path.ArcSize.kSmall_ArcSize
            direction = skia.PathDirection.kCW if command.sweep else skia.PathDirection.kCCW
            path.arcTo(command.rx, command.ry, command.rotation, size, direction, command.x, command.y)
        elif isinstance(command, ClosePath):
            path.close()
    if evenodd:
        path.setFillType(skia.PathFillType.kEvenOdd)
    return path


def from_skia(path: Any) -> PathData:
    """Read a ``skia.Path`` back as absolute M/L/Q/C/Z path data.

    Even-odd results are rewritten to nonzero winding first, so the data
    fills correctly without a ``fill-rule``.
    """
    skia = require_skia("path conversion")
    if path.getFillType() != skia.PathFillType.kWinding:
        path = skia.AsWinding(path) or path
    verbs = skia.Path.Verb
    commands: list[Any] = []
    iterator = skia.Path.RawIter(path)
    while True:
        verb, points = iterator.next()
        if verb == verbs.kDone_Verb:
            break
        if verb == verbs.kMove_Verb:
            commands.append(MoveTo(points[0].x(), points[0].y()))
        elif verb == verbs.kLine_Verb:
            commands.append(LineTo(points[1].x(), points[1].y()))
        elif verb == verbs.kQuad_Verb:
            commands.append(QuadTo(points[1].x(), points[1].y(), points[2].x(), points[2].y()))
        elif verb == verbs.kConic_Verb:
            quads = skia.Path.ConvertConicToQuads(points[0], points[1], points[2], iterator.conicWeight(), CONIC_SUBDIVISION)
            for index in range(1, len(quads) - 1, 2):
                control, end = quads[index], quads[index + 1]
                commands.append(QuadTo(control.x(), control.y(), end.x(), end.y()))
        elif verb == verbs.kCubic_Verb:
            c1, c2, end = points[1], points[2], points[3]
            commands.append(CurveTo(c1.x(), c1.y(), c2.x(), c2.y(), end.x(), end.y()))
        elif verb == verbs.kClose_Verb:
            commands.append(ClosePath())
    return PathData(commands)
