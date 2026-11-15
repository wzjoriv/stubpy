"""Color parsing and the ``<paint>`` type."""

from __future__ import annotations

from ._named import NAMED_COLORS
from .color import Color, clamp, parse_color
from .paint import Paint, PaintKeyword, PaintRef, PaintValue, parse_paint

__all__ = [
    "NAMED_COLORS",
    "Color",
    "Paint",
    "PaintKeyword",
    "PaintRef",
    "PaintValue",
    "clamp",
    "parse_color",
    "parse_paint",
]
