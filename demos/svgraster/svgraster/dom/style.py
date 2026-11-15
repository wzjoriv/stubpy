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
    "dominant-baseline": "auto",
    "font-family": "sans-serif",
    "font-size": "medium",
    "font-stretch": "normal",
    "font-style": "normal",
    "font-variant": "normal",
    "font-weight": "normal",
    "image-rendering": "auto",
    "kerning": "auto",
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
    "word-spacing": "normal",
    "writing-mode": "lr-tb",
}

NOT_INHERITED = {
    "alignment-baseline": "auto",
    "baseline-shift": "baseline",
    "clip-path": "none",
    "display": "inline",
    "enable-background": "accumulate",
    "filter": "none",
    "flood-color": "black",
    "flood-opacity": "1",
    "lighting-color": "white",
    "mask": "none",
    "opacity": "1",
    "overflow": "visible",
    "stop-color": "black",
    "stop-opacity": "1",
    "text-decoration": "none",
}

PROPERTIES = frozenset(INHERITED) | frozenset(NOT_INHERITED)
MARKER_PROPERTIES = ("marker-start", "marker-mid", "marker-end")
FONT_STYLES = frozenset({"italic", "oblique"})
FONT_WEIGHTS = frozenset({"bold", "bolder", "lighter", "100", "200", "300", "400", "500", "600", "700",
                          "800", "900"})


def expand_font(value: str) -> dict[str, str]:
    """Longhands of the CSS ``font`` shorthand (``[style] [variant] [weight] size[/height] family``)."""
    words = value.replace("/", " / ").split()
    out = {"font-style": "normal", "font-variant": "normal", "font-weight": "normal"}
    for i, word in enumerate(words):
        low = word.lower()
        if low in FONT_STYLES:
            out["font-style"] = low
        elif low == "small-caps":
            out["font-variant"] = low
        elif low in FONT_WEIGHTS:
            out["font-weight"] = low
        elif low == "normal":
            continue
        else:
            out["font-size"] = word
            rest = words[i + 1:]
            if rest[:1] == ["/"]:
                rest = rest[2:]
            if rest:
                out["font-family"] = " ".join(rest)
            return out
    return {}


def specified_style(node, sheet: Stylesheet) -> dict[str, str]:
    """Cascade presentation attributes, stylesheet rules and ``style``."""
    normal: dict[str, str] = {}
    important: dict[str, str] = {}
    for name in PROPERTIES & node.attrs.keys():
        normal[name] = node.attrs[name].strip()
    if "marker" in node.attrs:
        for key in MARKER_PROPERTIES:
            normal.setdefault(key, node.attrs["marker"].strip())
    declarations = [d for rule in sheet.matching(node) for d in rule.declarations]
    declarations += parse_declarations(node.attrs.get("style", ""))
    for decl in declarations:
        target = important if decl.important else normal
        if decl.name == "marker":
            target.update(dict.fromkeys(MARKER_PROPERTIES, decl.value))
        elif decl.name == "font":
            target.update(expand_font(decl.value))
        elif decl.name in PROPERTIES:
            target[decl.name] = decl.value
    normal.update(important)
    normal.update(getattr(node, "animated", None) or {})
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
