"""Text: content and ``xml:space``, font resolution, glyph layout, ``textPath`` and decorations."""
from __future__ import annotations

from itertools import groupby

from ...dom.node import Node
from ._decoration import Decoration, decorations
from ._fonts import DocumentFonts, document_fonts
from ._layout import Glyph, TextLayout

FONT_DB_KEY = "font-database"
LAYOUT_KEY = "text-layouts"


def layout_for(node: Node, viewport, document) -> TextLayout:
    """The (cached) layout of a ``text`` element."""
    cache = document.cache.setdefault(LAYOUT_KEY, {})
    key = (id(node), tuple(viewport))
    hit = cache.get(key)
    if hit is None or hit[0] is not node:
        fonts = document_fonts(document, document.cache.get(FONT_DB_KEY))
        hit = cache[key] = (node, TextLayout(node, viewport, fonts, document))
    return hit[1]


def text_bounds(node: Node, viewport, document) -> tuple[float, float, float, float] | None:
    """Union of the glyph cells of a ``text`` element in its user space."""
    return layout_for(node, viewport, document).bounds() if document is not None else None


def glyph_runs(layout: TextLayout, tolerance: float):
    """``(owner, glyphs, polygons)`` for consecutive visible glyphs sharing an owner."""
    visible = [g for g in layout.glyphs if g.visible]
    for owner, group in groupby(visible, key=lambda g: g.owner):
        glyphs = list(group)
        polys = [p for g in glyphs for p in g.font.glyph_polygons(g.gid, g.matrix, tolerance)]
        yield owner, glyphs, polys


__all__ = [
    "Decoration",
    "DocumentFonts",
    "Glyph",
    "TextLayout",
    "decorations",
    "document_fonts",
    "glyph_runs",
    "layout_for",
    "text_bounds",
]
