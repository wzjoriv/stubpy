"""Attribute groups shared by many elements.

Each group is a cooperative base: it takes its own keywords and forwards
the rest with ``super().__init__(*args, **kwargs)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .._internal._helpers import chainable
from .._internal._typing import FillRule, LineCap, Opacity
from ..attributes.descriptors import Attr
from ..attributes.length import Length, LengthLike
from ..color import PaintValue, parse_paint
from ..transform import Transform, TransformLike, as_transform
from .base import Child, Element

__all__ = [
    "CoreAttributes",
    "GraphicsElement",
    "PresentationAttributes",
    "StyleAttributes",
    "Transformable",
    "XLinkAttributes",
]


def _words(value: str | Sequence[str] | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return " ".join(value)


class CoreAttributes(Element):
    """``xml:base`` and ``xml:lang``."""

    def __init__(self, *args: Child, xml_base: str | None = None, xml_lang: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.update(xml_base=xml_base, xml_lang=xml_lang)


class StyleAttributes(Element):
    """``class`` and ``style``."""

    def __init__(
        self,
        *args: Child,
        class_: str | Sequence[str] | None = None,
        style: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(class_=_words(class_), style=style)

    @property
    def classes(self) -> list[str]:
        return str(self.attributes.get("class", "")).split()

    @chainable
    def add_class(self, *names: str) -> None:
        merged = self.classes + [n for n in names if n not in self.classes]
        self.attributes["class"] = " ".join(merged)


class PresentationAttributes(StyleAttributes):
    """The common presentation attributes; any other one goes through ``**kwargs``."""

    fill = Attr[PaintValue](convert=parse_paint)
    stroke = Attr[PaintValue](convert=parse_paint)
    stroke_width = Attr[Length](convert=Length.parse)
    opacity = Attr[float](convert=float)

    def __init__(
        self,
        *args: Child,
        fill: PaintValue = None,
        fill_opacity: Opacity | None = None,
        fill_rule: FillRule | None = None,
        stroke: PaintValue = None,
        stroke_width: LengthLike | None = None,
        stroke_linecap: LineCap | None = None,
        stroke_dasharray: Sequence[float] | str | None = None,
        opacity: Opacity | None = None,
        display: str | None = None,
        filter: str | Element | None = None,
        font_family: str | None = None,
        font_size: LengthLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(
            fill=fill,
            fill_opacity=fill_opacity,
            fill_rule=fill_rule,
            stroke=stroke,
            stroke_width=stroke_width,
            stroke_linecap=stroke_linecap,
            stroke_dasharray=tuple(stroke_dasharray) if isinstance(stroke_dasharray, (list, tuple)) else stroke_dasharray,
            opacity=opacity,
            display=display,
            filter=filter,
            font_family=font_family,
            font_size=font_size,
        )


class XLinkAttributes(Element):
    """``xlink:href`` and ``xlink:title``."""

    def __init__(self, *args: Child, href: str | Element | None = None, xlink_title: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.update(xlink_href=href, xlink_title=xlink_title)

    @property
    def target(self) -> str | None:
        """The referenced id for local ``#id`` links."""
        raw = self.attributes.get("xlink:href")
        text = None if raw is None else str(raw)
        return text[1:] if text and text.startswith("#") else None


class Transformable(Element):
    """Elements with a ``transform`` attribute."""

    def __init__(self, *args: Child, transform: TransformLike | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if transform is not None:
            self.transform = transform

    @property
    def transform(self) -> Transform:
        raw = self.attributes.get("transform")
        return Transform() if raw is None else as_transform(raw)

    @transform.setter
    def transform(self, value: TransformLike | None) -> None:
        if value is None:
            self.attributes.pop("transform", None)
        else:
            self.attributes["transform"] = as_transform(value)


class GraphicsElement(Transformable, PresentationAttributes, CoreAttributes):
    """Rendered element carrying every common attribute group."""
