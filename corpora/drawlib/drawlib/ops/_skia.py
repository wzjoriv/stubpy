"""Loading skia-python and combining outlines with it."""

from __future__ import annotations

import importlib
from functools import cache
from typing import TYPE_CHECKING, Any, Final, TypeAlias, Union

from ..path.commands import ClosePath, CurveTo, LineTo, MoveTo
from ..path.data import PathData

if TYPE_CHECKING:
    from ..elements._geometry import PathOperand

__all__ = ["INSTALL_HINT", "Geometry", "MissingDependencyError", "available", "combine", "require_skia"]

INSTALL_HINT: Final = "pip install 'drawlib[ops]'  (or: pip install skia-python)"

Geometry: TypeAlias = Union["PathOperand", PathData, str]
"""Anything with an outline: a shape, path data or ``d`` text."""


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


def _to_skia(item: Geometry) -> Any:
    from ..elements._geometry import PathOperand

    data = item.outline() if isinstance(item, PathOperand) else PathData(item) if isinstance(item, str) else item
    path = require_skia("path conversion").Path()
    for command in data:
        if isinstance(command, MoveTo):
            path.moveTo(command.x, command.y)
        elif isinstance(command, LineTo):
            path.lineTo(command.x, command.y)
        elif isinstance(command, CurveTo):
            path.cubicTo(command.x1, command.y1, command.x2, command.y2, command.x, command.y)
        elif isinstance(command, ClosePath):
            path.close()
    return path


def combine(first: Geometry, second: Geometry, op: str) -> PathData:
    """Boolean combination of two outlines: ``union``, ``intersection``, ``difference`` or ``xor``."""
    skia = require_skia("boolean operations")
    kinds = {
        "union": skia.PathOp.kUnion_PathOp,
        "intersection": skia.PathOp.kIntersect_PathOp,
        "difference": skia.PathOp.kDifference_PathOp,
        "xor": skia.PathOp.kXOR_PathOp,
    }
    result = skia.Op(_to_skia(first), _to_skia(second), kinds[op])
    commands: list[Any] = []
    for verb, points in skia.Path.RawIter(result):
        if verb == skia.Path.Verb.kMove_Verb:
            commands.append(MoveTo(points[0].x(), points[0].y()))
        elif verb == skia.Path.Verb.kLine_Verb:
            commands.append(LineTo(points[1].x(), points[1].y()))
        elif verb == skia.Path.Verb.kClose_Verb:
            commands.append(ClosePath())
    return PathData(commands)
