"""Functional API: lowercase constructors, composite shapes and effects."""

from __future__ import annotations

from ._effects import arrow_marker, drawing, drop_shadow, glow
from ._functions import (
    circle,
    dashed_line,
    document,
    dot,
    ellipse,
    group,
    line,
    linear_gradient,
    outline,
    path,
    polygon,
    polyline,
    radial_gradient,
    rect,
    square,
    text,
    use,
)
from ._shapes import SHAPES, arrow, gear, regular_polygon, shape_factory, star

__all__ = [
    "SHAPES",
    "arrow",
    "arrow_marker",
    "circle",
    "dashed_line",
    "document",
    "dot",
    "drawing",
    "drop_shadow",
    "ellipse",
    "gear",
    "glow",
    "group",
    "line",
    "linear_gradient",
    "outline",
    "path",
    "polygon",
    "polyline",
    "radial_gradient",
    "rect",
    "regular_polygon",
    "shape_factory",
    "square",
    "star",
    "text",
    "use",
]
