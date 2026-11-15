"""Geometry backed by the optional skia-python dependency.

Install with ``pip install 'svgwriter[ops]'``. The module always imports;
each function raises :class:`MissingDependencyError` when skia-python is
missing. The same features are reachable from elements: ``a | b``,
``a & b``, ``a - b``, ``a ^ b``, ``shape.total_length()``,
``shape.contains_point(x, y)`` and so on.

Example
-------
>>> import svgwriter as svg
>>> from svgwriter import ops
>>> ring = svg.Circle(50, 50, 40) - svg.Circle(50, 50, 20)   # doctest: +SKIP
>>> ops.contains(ring, 50, 50)                              # doctest: +SKIP
False
"""

from __future__ import annotations

from ._skia import INSTALL_HINT, Geometry, MissingDependencyError, available, from_skia, to_skia
from .boolean import BooleanOp, combine, difference, intersection, simplify, union, xor
from .measure import Cap, Join, bounds, contains, point_at_length, stroke_to_path, tangent_at_length, total_length
from .render import rasterize, skia_renderer
from .text import Anchor, FontWeight, text_outline, text_to_path, text_width

__all__ = [
    "INSTALL_HINT",
    "Anchor",
    "BooleanOp",
    "Cap",
    "FontWeight",
    "Geometry",
    "Join",
    "MissingDependencyError",
    "available",
    "bounds",
    "combine",
    "contains",
    "difference",
    "from_skia",
    "intersection",
    "point_at_length",
    "rasterize",
    "simplify",
    "skia_renderer",
    "stroke_to_path",
    "tangent_at_length",
    "text_outline",
    "text_to_path",
    "text_width",
    "to_skia",
    "total_length",
    "union",
    "xor",
]
