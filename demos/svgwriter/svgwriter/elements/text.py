"""Text content elements."""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any, Union

from .._internal._constants import DEFAULT_PRECISION
from .._internal._typing import LengthAdjust
from ..attributes.length import LengthLike
from ._mixins import (
    ConditionalAttributes,
    CoreAttributes,
    GraphicsElement,
    PresentationAttributes,
    XLinkAttributes,
)
from .base import Category, Child, ContentModel, Element
from .container import Container

__all__ = [
    "AltGlyph",
    "AltGlyphDef",
    "AltGlyphItem",
    "GlyphRef",
    "TRef",
    "TSpan",
    "Text",
    "TextDecoration",
    "TextPath",
]

Coordinates = Union[LengthLike, Sequence[LengthLike]]


class TextDecoration(enum.Flag):
    """``text-decoration`` keywords; combine with ``|``."""

    NONE = 0
    UNDERLINE = enum.auto()
    OVERLINE = enum.auto()
    LINE_THROUGH = enum.auto()
    BLINK = enum.auto()

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        words = [m.name.lower().replace("_", "-") for m in TextDecoration if m.value and m in self]  # type: ignore[union-attr]
        return " ".join(words) or "none"


def _coords(value: Coordinates | None) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


class _TextPositioning(Element):
    """``x``, ``y``, ``dx``, ``dy`` and ``rotate``, each a number or list."""

    def __init__(
        self,
        *args: Child,
        x: Coordinates | None = None,
        y: Coordinates | None = None,
        dx: Coordinates | None = None,
        dy: Coordinates | None = None,
        rotate: float | Sequence[float] | None = None,
        **kwargs: Any,
    ) -> None:
        decoration = kwargs.pop("decoration", None)
        super().__init__(*args, **kwargs)
        self.update(x=_coords(x), y=_coords(y), dx=_coords(dx), dy=_coords(dy), rotate=_coords(rotate))
        if decoration is not None:
            self.set("text-decoration", decoration)


class _TextLength(Element):
    def __init__(
        self,
        *args: Child,
        text_length: LengthLike | None = None,
        length_adjust: LengthAdjust | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(text_length=text_length, length_adjust=length_adjust)


class Text(GraphicsElement, _TextLength, _TextPositioning, tag="text", category=Category.TEXT_CONTENT, content=ContentModel.MIXED):
    """``<text>``.

    Parameters
    ----------
    *content : str or Element
        Text runs and ``tspan``/``tref``/``textPath``/``altGlyph`` children.
    **kwargs
        Positioning (``x``, ``y``, ``dx``, ``dy``, ``rotate``),
        ``text_length``, ``decoration`` (a :class:`TextDecoration`) and any
        presentation, conditional or core attribute.

    Examples
    --------
    >>> str(Text("Hi", x=10, y=20, decoration=TextDecoration.UNDERLINE))
    '<text x="10" y="20" text-decoration="underline">Hi</text>'
    """

    def span(self, text: str, **kwargs: Any) -> TSpan:
        """Append a ``<tspan>`` and return it."""
        return self.append(TSpan(text, **kwargs))


class TSpan(PresentationAttributes, ConditionalAttributes, CoreAttributes, _TextLength, _TextPositioning, tag="tspan", category=Category.TEXT_CONTENT, content=ContentModel.MIXED):
    """``<tspan>``: a sub-run of text with its own position or style."""


class TRef(XLinkAttributes, PresentationAttributes, ConditionalAttributes, CoreAttributes, _TextPositioning, tag="tref", category=Category.TEXT_CONTENT):
    """``<tref>``: the character data of a referenced element."""

    def __init__(self, href: str | Element | None = None, **kwargs: Any) -> None:
        super().__init__(href=href, **kwargs)


class TextPath(XLinkAttributes, PresentationAttributes, ConditionalAttributes, CoreAttributes, _TextLength, tag="textPath", category=Category.TEXT_CONTENT, content=ContentModel.MIXED):
    """``<textPath>``: text laid out along a path."""

    def __init__(
        self,
        *content: Child,
        href: str | Element | None = None,
        start_offset: LengthLike | None = None,
        method: str | None = None,
        spacing: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*content, href=href, **kwargs)
        self.update(start_offset=start_offset, method=method, spacing=spacing)


class AltGlyph(XLinkAttributes, PresentationAttributes, ConditionalAttributes, CoreAttributes, _TextPositioning, tag="altGlyph", category=Category.TEXT_CONTENT, content=ContentModel.TEXT):
    """``<altGlyph>``: substitute glyphs for its character data."""

    def __init__(
        self,
        text: str = "",
        *,
        href: str | Element | None = None,
        glyph_ref: str | None = None,
        format: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*([text] if text else []), href=href, **kwargs)
        self.update(glyph_ref=glyph_ref, format=format)


class GlyphRef(XLinkAttributes, PresentationAttributes, CoreAttributes, tag="glyphRef", category=Category.TEXT_CONTENT, content=ContentModel.EMPTY):
    """``<glyphRef>``: one glyph of an ``altGlyphDef``."""

    def __init__(
        self,
        href: str | Element | None = None,
        *,
        glyph_ref: str | None = None,
        format: str | None = None,
        x: float | None = None,
        y: float | None = None,
        dx: float | None = None,
        dy: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(href=href, **kwargs)
        self.update(glyph_ref=glyph_ref, format=format, x=x, y=y, dx=dx, dy=dy)


class AltGlyphItem(CoreAttributes, Container[GlyphRef], tag="altGlyphItem", category=Category.TEXT_CONTENT):
    """``<altGlyphItem>``: one candidate set of glyph references."""


class AltGlyphDef(CoreAttributes, Container[Element], tag="altGlyphDef", category=Category.TEXT_CONTENT):
    """``<altGlyphDef>``: glyph substitutions for ``altGlyph``."""
