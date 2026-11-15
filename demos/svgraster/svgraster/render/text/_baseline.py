"""Baselines, baseline shifts and spacing for laid-out glyphs."""
from __future__ import annotations

from ...dom.node import Node
from ...dom.units import parse_length

SUPER_EM = 1.0 / 3.0
SUB_EM = -0.2
DEFAULT_X_HEIGHT_EM = 0.5
HANGING_ASCENT = 0.8
MATH_ASCENT = 0.5
EDGE_BASELINES = {"text-before-edge": "ascent", "text-top": "ascent", "before-edge": "ascent",
                  "text-after-edge": "descent", "text-bottom": "descent", "after-edge": "descent",
                  "ideographic": "descent"}


def spacing(node: Node, prop: str, viewport) -> float:
    value = node.style.get(prop, "normal")
    if value in ("normal", "auto"):
        return 0.0
    return parse_length(value, node.units(viewport), "x", 0.0)


def baseline_shift(chain: tuple[Node, ...], viewport) -> float:
    total = 0.0
    for node in chain[1:]:
        value = node.specified.get("baseline-shift", "baseline").strip()
        if value == "baseline":
            continue
        if value == "super":
            total += node.font_size * SUPER_EM
        elif value == "sub":
            total += node.font_size * SUB_EM
        elif value.endswith("%"):
            total += node.font_size * float(value[:-1]) / 100.0
        else:
            total += parse_length(value, node.units(viewport), "y", 0.0)
    return total


def baseline_offset(owner: Node, font, size: float) -> float:
    key = owner.style.get("alignment-baseline", "auto")
    if key in ("auto", "baseline", "inherit"):
        key = owner.style.get("dominant-baseline", "auto")
    m = font.metrics
    s = size / font.units_per_em
    if key in ("middle",):
        return (m.x_height or DEFAULT_X_HEIGHT_EM * font.units_per_em) / 2 * s
    if key in ("central",):
        return (m.ascent + m.descent) / 2 * s
    if key == "hanging":
        return HANGING_ASCENT * m.ascent * s
    if key == "mathematical":
        return MATH_ASCENT * m.ascent * s
    if key in EDGE_BASELINES:
        return (m.ascent if EDGE_BASELINES[key] == "ascent" else m.descent) * s
    return 0.0


def pick(fonts, style, ch: str):
    matches = fonts.matches(style)
    for match in matches:
        if ch.isspace() or match.font.has_glyph(ch):
            return match
    return fonts.fallback(ch, style) or matches[-1]
