"""Painting laid-out text: glyph fills and strokes, synthetic bold and decorations."""
from __future__ import annotations

from ...dom.node import Node
from ...dom.units import parse_fraction
from ...parse.flatten import Polyline
from ...raster.stroke import stroke_polylines
from .._geometry import BBox
from ._decoration import decorations
from ._layout import TextLayout

SYNTHETIC_BOLD_EM = 0.04
UNDER_TEXT = ("underline", "overline")
ROUND = "round"


def _unit(value: float) -> float:
    return min(1.0, max(0.0, value))


def paint_outlines(drawer, node: Node, polys, target, ctm, viewport, bbox, extra_width: float = 0.0) -> None:
    """Fill ``polys`` with ``node``'s fill (thickened by ``extra_width``), then stroke them."""
    style = node.style
    if style.get("visibility", "visible") != "visible" or not polys:
        return
    fill_opacity = _unit(parse_fraction(style.get("fill-opacity"), 1.0))
    drawer.fill_area(target, polys, ctm, "nonzero", node, "fill", fill_opacity, bbox, viewport)
    if extra_width > 0:
        outline = stroke_polylines([(p, True) for p in polys], extra_width, ROUND, ROUND,
                                   tolerance=drawer.user_tolerance(ctm))
        drawer.fill_area(target, outline, ctm, "nonzero", node, "fill", fill_opacity, bbox, viewport)
    if style.get("stroke", "none") != "none":
        outline = drawer.stroke_outline(node, [Polyline(p, True) for p in polys], ctm, viewport)
        stroke_opacity = _unit(parse_fraction(style.get("stroke-opacity"), 1.0))
        drawer.fill_area(target, outline, ctm, "nonzero", node, "stroke", stroke_opacity, bbox, viewport)


def paint_text(drawer, layout: TextLayout, target, ctm, viewport) -> None:
    """Underlines and overlines, then glyph runs, then line-throughs."""
    from . import glyph_runs

    bounds = layout.bounds()
    bbox = BBox.from_bounds(bounds) if bounds is not None else None
    decos = decorations(layout)
    for deco in decos:
        if deco.kind in UNDER_TEXT:
            paint_outlines(drawer, deco.node, [deco.polygon], target, ctm, viewport, bbox)
    for owner, glyphs, polys in glyph_runs(layout, drawer.user_tolerance(ctm)):
        bold = all(g.synthetic_bold for g in glyphs)
        paint_outlines(drawer, owner, polys, target, ctm, viewport, bbox,
                       owner.font_size * SYNTHETIC_BOLD_EM if bold else 0.0)
    for deco in decos:
        if deco.kind not in UNDER_TEXT:
            paint_outlines(drawer, deco.node, [deco.polygon], target, ctm, viewport, bbox)
