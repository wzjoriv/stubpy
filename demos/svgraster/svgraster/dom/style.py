"""Presentation properties: initial values, inheritance and the cascade."""
from __future__ import annotations

from .css import Stylesheet, parse_declarations
from .units import DEFAULT_FONT_SIZE, UnitContext, parse_length, split_length

INHERIT = "inherit"
FONT_SIZE_KEYWORDS = {
    "xx-small": 9.0, "x-small": 10.0, "small": 13.0, "medium": 16.0,
    "large": 18.0, "x-large": 24.0, "xx-large": 32.0,
}
RELATIVE_FONT_STEP = 1.2

INHERITED = {
    "clip-rule": "nonzero",
    "color": "black",
    "color-interpolation": "sRGB",
    "color-interpolation-filters": "linearRGB",
    "fill": "black",
    "fill-opacity": "1",
    "fill-rule": "nonzero",
    "font-family": "sans-serif",
    "font-size": "medium",
    "font-style": "normal",
    "font-weight": "normal",
    "letter-spacing": "normal",
    "marker-start": "none",
    "marker-mid": "none",
    "marker-end": "none",
    "stroke": "none",
    "stroke-dasharray": "none",
    "stroke-dashoffset": "0",
    "stroke-linecap": "butt",
    "stroke-linejoin": "miter",
    "stroke-miterlimit": "4",
    "stroke-opacity": "1",
    "stroke-width": "1",
    "text-anchor": "start",
    "visibility": "visible",
}

NOT_INHERITED = {
    "clip-path": "none",
    "display": "inline",
    "filter": "none",
    "flood-color": "black",
    "flood-opacity": "1",
    "lighting-color": "white",
    "mask": "none",
    "opacity": "1",
    "overflow": "visible",
    "stop-color": "black",
    "stop-opacity": "1",
}

PROPERTIES = frozenset(INHERITED) | frozenset(NOT_INHERITED)


def specified_style(node, sheet: Stylesheet) -> dict[str, str]:
    """Cascade presentation attributes, stylesheet rules and ``style``."""
    normal: dict[str, str] = {}
    important: dict[str, str] = {}
    for name in PROPERTIES & node.attrs.keys():
        normal[name] = node.attrs[name].strip()
    if "marker" in node.attrs:
        for key in ("marker-start", "marker-mid", "marker-end"):
            normal.setdefault(key, node.attrs["marker"].strip())
    declarations = [d for rule in sheet.matching(node) for d in rule.declarations]
    declarations += parse_declarations(node.attrs.get("style", ""))
    for decl in declarations:
        names = ("marker-start", "marker-mid", "marker-end") if decl.name == "marker" else (decl.name,)
        for name in names:
            if name in PROPERTIES:
                (important if decl.important else normal)[name] = decl.value
    normal.update(important)
    return normal


def _font_size(value: str, parent_size: float) -> float:
    value = value.strip().lower()
    if value in FONT_SIZE_KEYWORDS:
        return FONT_SIZE_KEYWORDS[value]
    if value == "larger":
        return parent_size * RELATIVE_FONT_STEP
    if value == "smaller":
        return parent_size / RELATIVE_FONT_STEP
    try:
        number, unit = split_length(value)
    except ValueError:
        return parent_size
    if unit == "%":
        return parent_size * number / 100.0
    return parse_length(value, UnitContext(font_size=parent_size), default=parent_size)


def computed_style(specified: dict[str, str], parent: dict[str, str] | None,
                   parent_font_size: float = DEFAULT_FONT_SIZE) -> tuple[dict[str, str], float]:
    """Resolve ``inherit`` and inheritance; return the style and font size."""
    parent = parent or {}
    style = {}
    for name, initial in INHERITED.items():
        value = specified.get(name, INHERIT)
        style[name] = parent.get(name, initial) if value == INHERIT else value
    for name, initial in NOT_INHERITED.items():
        value = specified.get(name, initial)
        style[name] = parent.get(name, initial) if value == INHERIT else value
    font_size = _font_size(style["font-size"], parent_font_size) if "font-size" in specified else parent_font_size
    return style, font_size
