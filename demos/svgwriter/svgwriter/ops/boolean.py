"""Boolean path operations (union, intersection, difference, xor)."""

from __future__ import annotations

import enum

from ..path.data import PathData
from ._skia import Geometry, from_skia, geometry_data, require_skia, to_skia

__all__ = ["BooleanOp", "combine", "difference", "intersection", "simplify", "union", "xor"]


class BooleanOp(enum.Enum):
    """How :func:`combine` merges two outlines."""

    UNION = "kUnion_PathOp"
    INTERSECTION = "kIntersect_PathOp"
    DIFFERENCE = "kDifference_PathOp"
    REVERSE_DIFFERENCE = "kReverseDifference_PathOp"
    XOR = "kXOR_PathOp"


def combine(first: Geometry, second: Geometry, op: BooleanOp) -> PathData:
    """Combine two outlines with a boolean operation.

    Parameters
    ----------
    first, second : shape, text, PathData or str
        Outlines in user units; each element's own ``transform`` and
        ``fill-rule`` are honoured.
    op : BooleanOp
        The operation.

    Returns
    -------
    PathData
        The resulting outline (lines, quadratics and cubics).

    Raises
    ------
    MissingDependencyError
        When skia-python is not installed.
    """
    skia = require_skia(f"boolean path operation {op.name.lower()}")
    a_data, a_evenodd = geometry_data(first)
    b_data, b_evenodd = geometry_data(second)
    result = skia.Op(to_skia(a_data, evenodd=a_evenodd), to_skia(b_data, evenodd=b_evenodd), getattr(skia.PathOp, op.value))
    if result is None:
        raise ValueError(f"skia could not compute the {op.name.lower()} of these outlines")
    return from_skia(result)


def union(first: Geometry, *others: Geometry) -> PathData:
    """Area covered by any of the outlines."""
    if not others:
        return simplify(first)
    result = combine(first, others[0], BooleanOp.UNION)
    for item in others[1:]:
        result = combine(result, item, BooleanOp.UNION)
    return result


def intersection(first: Geometry, second: Geometry) -> PathData:
    """Area covered by both outlines."""
    return combine(first, second, BooleanOp.INTERSECTION)


def difference(first: Geometry, second: Geometry) -> PathData:
    """Area of *first* not covered by *second*."""
    return combine(first, second, BooleanOp.DIFFERENCE)


def xor(first: Geometry, second: Geometry) -> PathData:
    """Area covered by exactly one of the outlines."""
    return combine(first, second, BooleanOp.XOR)


def simplify(item: Geometry) -> PathData:
    """Equivalent outline with no self-intersections or overlaps."""
    skia = require_skia("path simplification")
    data, evenodd = geometry_data(item)
    result = skia.Simplify(to_skia(data, evenodd=evenodd))
    if result is None:
        raise ValueError("skia could not simplify this outline")
    return from_skia(result)
