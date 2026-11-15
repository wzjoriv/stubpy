"""``image``, ``style``, ``script``, ``foreignObject``, ``view``, ``cursor``
and ``color-profile``."""

from __future__ import annotations

from typing import Any

from ...attributes.length import LengthLike
from ...attributes.style import StyleSheet
from ...attributes.viewbox import PreserveAspectRatio
from .._mixins import (
    ConditionalAttributes,
    CoreAttributes,
    ExternalResourcesAttribute,
    GraphicsElement,
    XLinkAttributes,
)
from .._viewport import FitToViewBox, Positioned
from ..base import Category, Child, ContentModel, Element

__all__ = ["ColorProfile", "Cursor", "ForeignObject", "Image", "Script", "StyleElement", "View"]


class Image(GraphicsElement, XLinkAttributes, Positioned, tag="image", category=Category.GRAPHICS, content=ContentModel.ELEMENTS):
    """``<image>``: a raster image or external SVG."""

    def __init__(
        self,
        href: str | None = None,
        x: LengthLike | None = None,
        y: LengthLike | None = None,
        width: LengthLike | None = None,
        height: LengthLike | None = None,
        *,
        preserve_aspect_ratio: PreserveAspectRatio | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(href=href, x=x, y=y, width=width, height=height, **kwargs)
        self.update(preserve_aspect_ratio=preserve_aspect_ratio)


class StyleElement(CoreAttributes, tag="style", content=ContentModel.TEXT):
    """``<style>``: an embedded style sheet."""

    def __init__(
        self,
        css: str | StyleSheet = "",
        *,
        type: str = "text/css",
        media: str | None = None,
        title: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(type=type, media=media, title=title)
        self.text = css  # type: ignore[assignment]

    @property
    def text(self) -> str:
        return super().text

    @text.setter
    def text(self, value: str | StyleSheet) -> None:
        Element.text.fset(self, value.css() if isinstance(value, StyleSheet) else value)  # type: ignore[attr-defined]


class Script(XLinkAttributes, ExternalResourcesAttribute, CoreAttributes, tag="script", content=ContentModel.TEXT):
    """``<script>``: inline code or a reference to it."""

    def __init__(self, code: str = "", *, type: str = "text/ecmascript", **kwargs: Any) -> None:
        super().__init__(*([code] if code else []), **kwargs)
        self.update(type=type)


class ForeignObject(GraphicsElement, Positioned, tag="foreignObject", category=Category.GRAPHICS, content=ContentModel.MIXED):
    """``<foreignObject>``: content from another XML namespace."""

    def __init__(self, *children: Child, **kwargs: Any) -> None:
        super().__init__(*children, **kwargs)


class View(FitToViewBox, ExternalResourcesAttribute, CoreAttributes, tag="view", content=ContentModel.EMPTY):
    """``<view>``: a named view into the document."""

    def __init__(self, *, view_target: str | None = None, zoom_and_pan: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(view_target=view_target, zoom_and_pan=zoom_and_pan)


class Cursor(XLinkAttributes, ConditionalAttributes, ExternalResourcesAttribute, CoreAttributes, tag="cursor", content=ContentModel.ELEMENTS):
    """``<cursor>``: a PNG or SVG cursor image with a hot spot."""

    def __init__(self, href: str | None = None, x: LengthLike = 0, y: LengthLike = 0, **kwargs: Any) -> None:
        super().__init__(href=href, **kwargs)
        self.update(x=x, y=y)


class ColorProfile(XLinkAttributes, CoreAttributes, tag="color-profile", content=ContentModel.ELEMENTS):
    """``<color-profile>``: an ICC profile referenced by ``icc-color``."""

    def __init__(
        self,
        name: str,
        href: str | None = None,
        *,
        local: str | None = None,
        rendering_intent: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(href=href, **kwargs)
        self.update(local=local, name=name, rendering_intent=rendering_intent)
