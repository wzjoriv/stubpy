"""Text outlines and measurement from installed fonts."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Final, Literal

from ..path.data import PathData
from ._skia import from_skia, require_skia

if TYPE_CHECKING:
    from ..elements.shapes import Path

__all__ = ["Anchor", "FontWeight", "text_outline", "text_to_path", "text_width"]

Anchor = Literal["start", "middle", "end"]
FontWeight = int | Literal["normal", "bold"]

DEFAULT_FAMILY: Final = "sans-serif"
DEFAULT_SIZE: Final = 16.0
NORMAL_WEIGHT: Final = 400
BOLD_WEIGHT: Final = 700
NORMAL_WIDTH: Final = 5
GENERIC_FAMILIES: Final = frozenset({"serif", "sans-serif", "monospace", "cursive", "fantasy"})
_ANCHOR_SHIFT: Final = {"start": 0.0, "middle": 0.5, "end": 1.0}


def _weight(value: FontWeight) -> int:
    if value == "normal":
        return NORMAL_WEIGHT
    if value == "bold":
        return BOLD_WEIGHT
    return int(value)


def _font(font_family: str, size: float, weight: FontWeight, italic: bool) -> Any:
    skia = require_skia("text outlines")
    slant = skia.FontStyle.kItalic_Slant if italic else skia.FontStyle.kUpright_Slant
    families = [name.strip().strip("'\"") for name in font_family.split(",") if name.strip()]
    typeface = None
    for family in families or [DEFAULT_FAMILY]:
        candidate = skia.Typeface(family, skia.FontStyle(_weight(weight), NORMAL_WIDTH, slant))
        if family.lower() in GENERIC_FAMILIES or candidate.getFamilyName().lower() == family.lower():
            typeface = candidate
            break
    if typeface is None:
        typeface = skia.Typeface(families[-1], skia.FontStyle(_weight(weight), NORMAL_WIDTH, slant))
        warnings.warn(
            f"font {font_family!r} not found; using {typeface.getFamilyName()!r}",
            stacklevel=3,
        )
    return skia.Font(typeface, size)


def text_width(
    text: str,
    font_family: str = DEFAULT_FAMILY,
    size: float = DEFAULT_SIZE,
    *,
    weight: FontWeight = "normal",
    italic: bool = False,
) -> float:
    """Advance width of *text* set in the given font."""
    return float(_font(font_family, size, weight, italic).measureText(text))


def text_outline(
    text: str,
    font_family: str = DEFAULT_FAMILY,
    size: float = DEFAULT_SIZE,
    *,
    x: float = 0.0,
    y: float = 0.0,
    anchor: Anchor = "start",
    weight: FontWeight = "normal",
    italic: bool = False,
) -> PathData:
    """Glyph outlines of *text* as path data, baseline at ``(x, y)``.

    ``font_family`` may be a CSS-style list (``"Inter, Arial, sans-serif"``);
    the first installed family wins.
    """
    skia = require_skia("text outlines")
    font = _font(font_family, size, weight, italic)
    glyphs = font.textToGlyphs(text)
    origin_x = x - _ANCHOR_SHIFT[anchor] * font.measureText(text)
    combined = skia.Path()
    for glyph, position in zip(glyphs, font.getPos(glyphs, skia.Point(origin_x, y))):
        outline = font.getPath(glyph)
        if outline is not None:
            combined.addPath(outline, position.x(), position.y())
    return from_skia(combined)


def text_to_path(
    text: str,
    font_family: str = DEFAULT_FAMILY,
    size: float = DEFAULT_SIZE,
    *,
    x: float = 0.0,
    y: float = 0.0,
    anchor: Anchor = "start",
    weight: FontWeight = "normal",
    italic: bool = False,
    **kwargs: Any,
) -> Path:
    """A ``<path>`` tracing the glyphs of *text*.

    Parameters
    ----------
    text : str
        The characters to outline.
    font_family : str
        Family name or comma-separated fallback list.
    size : float
        Font size in user units.
    x, y : float
        Baseline position of the anchor point.
    anchor : {"start", "middle", "end"}
        Horizontal alignment, as ``text-anchor``.
    weight : int or {"normal", "bold"}
        Font weight.
    italic : bool
        Use the italic style.
    **kwargs
        Attributes for the :class:`~svgwriter.Path`.

    Raises
    ------
    MissingDependencyError
        When skia-python is not installed.
    """
    from ..elements.shapes import Path

    data = text_outline(text, font_family, size, x=x, y=y, anchor=anchor, weight=weight, italic=italic)
    return Path(data, **kwargs)
