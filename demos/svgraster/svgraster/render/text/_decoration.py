"""``text-decoration`` lines (underline, overline, line-through) for laid-out glyphs."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...dom.node import Node
from ._layout import TextLayout

KINDS = ("underline", "overline", "line-through")
DEFAULT_THICKNESS_EM = 0.05
DEFAULT_STRIKE_EM = 0.3


@dataclass
class Decoration:
    """One decoration rectangle painted with ``node``'s fill and stroke."""

    node: Node
    kind: str
    polygon: np.ndarray


def _decorators(chain: tuple[Node, ...]) -> list[Node]:
    return [n for n in chain if n.style.get("text-decoration", "none") not in ("none", "")]


def _line(kind: str, font, size: float) -> tuple[float, float]:
    m, upm = font.metrics, font.units_per_em
    s = size / upm
    thick = (m.underline_thickness or DEFAULT_THICKNESS_EM * upm) * s
    if kind == "underline":
        return -m.underline_position * s, thick
    if kind == "overline":
        return -m.ascent * s, thick
    strike = m.strikeout_position or DEFAULT_STRIKE_EM * upm
    return -strike * s, (m.strikeout_size or m.underline_thickness or DEFAULT_THICKNESS_EM * upm) * s


def decorations(layout: TextLayout) -> list[Decoration]:
    """Decoration rectangles grouped by decorating element and text chunk."""
    groups: dict[tuple[int, int], list] = {}
    order: list[tuple[int, int]] = []
    for g in layout.glyphs:
        if g.on_path or not g.visible:
            continue
        for node in _decorators(g.char.chain):
            key = (id(node), g.chunk)
            if key not in groups:
                groups[key] = [node]
                order.append(key)
            groups[key].append(g)
    out = []
    for key in order:
        node, *glyphs = groups[key]
        font = layout.fonts.matches(node.style)[0].font
        x0 = min(g.x for g in glyphs)
        x1 = max(g.x + g.advance for g in glyphs)
        base = glyphs[0].y
        for kind in KINDS:
            if kind not in node.style.get("text-decoration", "").split():
                continue
            centre, thick = _line(kind, font, node.font_size)
            y0, y1 = base + centre - thick / 2.0, base + centre + thick / 2.0
            out.append(Decoration(node, kind, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)))
    return out
