"""Attribute groups shared by many elements (SVG 1.1, appendix M).

Each group is a cooperative base: it takes its own keywords and forwards
the rest with ``super().__init__(*args, **kwargs)``.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any

from .._internal._registry import chainable
from .._internal._typing import FillRule, LineCap, LineJoin, Opacity
from ..attributes.descriptors import Attr
from ..attributes.length import Length, LengthLike
from ..attributes.names import PRESENTATION_ATTRIBUTES
from ..attributes.style import Style, StyleLike
from ..color.paint import PaintValue, parse_paint
from ..transform.transform import Transform, TransformLike, as_transform
from .base import Child, Element

__all__ = [
    "ConditionalAttributes",
    "CoreAttributes",
    "ExternalResourcesAttribute",
    "GraphicsElement",
    "PresentationAttributes",
    "StyleAttributes",
    "Transformable",
    "XLinkAttributes",
    "XmlSpace",
]


class XmlSpace(str, enum.Enum):
    DEFAULT = "default"
    PRESERVE = "preserve"


def _words(value: str | Sequence[str] | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return " ".join(value)


class CoreAttributes(Element):
    """``id``, ``xml:base``, ``xml:lang`` and ``xml:space``."""

    def __init__(
        self,
        *args: Child,
        xml_base: str | None = None,
        xml_lang: str | None = None,
        xml_space: XmlSpace | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(xml_base=xml_base, xml_lang=xml_lang, xml_space=xml_space)


class ConditionalAttributes(Element):
    """``requiredFeatures``, ``requiredExtensions`` and ``systemLanguage``."""

    def __init__(
        self,
        *args: Child,
        required_features: str | Sequence[str] | None = None,
        required_extensions: str | Sequence[str] | None = None,
        system_language: str | Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(
            required_features=_words(required_features),
            required_extensions=_words(required_extensions),
            system_language=",".join(system_language) if isinstance(system_language, (list, tuple)) else system_language,
        )


class StyleAttributes(Element):
    """``class`` and ``style``."""

    def __init__(
        self,
        *args: Child,
        class_: str | Sequence[str] | None = None,
        style: StyleLike | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(class_=_words(class_))
        if style is not None:
            self.style = Style(style)

    @property
    def classes(self) -> list[str]:
        return str(self.attributes.get("class", "")).split()

    @chainable
    def add_class(self, *names: str) -> None:
        merged = self.classes + [n for n in names if n not in self.classes]
        self.attributes["class"] = " ".join(merged)

    @property
    def style(self) -> Style:
        """A copy of the ``style`` attribute; assign to change it."""
        raw = self.attributes.get("style")
        return Style(raw) if raw is not None else Style()

    @style.setter
    def style(self, value: StyleLike | None) -> None:
        style = Style(value) if value is not None else Style()
        if style:
            self.attributes["style"] = style
        else:
            self.attributes.pop("style", None)


class PresentationAttributes(StyleAttributes):
    """The presentation attributes, plus moving them to and from CSS.

    Common properties are explicit keywords; any other presentation
    attribute can be passed through ``**kwargs``.
    """

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
        stroke_opacity: Opacity | None = None,
        stroke_linecap: LineCap | None = None,
        stroke_linejoin: LineJoin | None = None,
        stroke_miterlimit: float | None = None,
        stroke_dasharray: Sequence[float] | str | None = None,
        stroke_dashoffset: LengthLike | None = None,
        opacity: Opacity | None = None,
        display: str | None = None,
        visibility: str | None = None,
        color: str | None = None,
        clip_path: str | Element | None = None,
        mask: str | Element | None = None,
        filter: str | Element | None = None,
        font_family: str | None = None,
        font_size: LengthLike | None = None,
        font_weight: str | int | None = None,
        text_anchor: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(
            fill=fill,
            fill_opacity=fill_opacity,
            fill_rule=fill_rule,
            stroke=stroke,
            stroke_width=stroke_width,
            stroke_opacity=stroke_opacity,
            stroke_linecap=stroke_linecap,
            stroke_linejoin=stroke_linejoin,
            stroke_miterlimit=stroke_miterlimit,
            stroke_dasharray=tuple(stroke_dasharray) if isinstance(stroke_dasharray, (list, tuple)) else stroke_dasharray,
            stroke_dashoffset=stroke_dashoffset,
            opacity=opacity,
            display=display,
            visibility=visibility,
            color=color,
            clip_path=clip_path,
            mask=mask,
            filter=filter,
            font_family=font_family,
            font_size=font_size,
            font_weight=font_weight,
            text_anchor=text_anchor,
        )

    def presentation(self) -> dict[str, Any]:
        """Presentation attributes currently set as XML attributes."""
        return {k: v for k, v in self.attributes.items() if k in PRESENTATION_ATTRIBUTES}

    @chainable
    def to_css(self) -> None:
        """Move presentation attributes into the ``style`` attribute."""
        style = self.style
        for name, value in self.presentation().items():
            style[name] = value
            del self.attributes[name]
        self.style = style

    @chainable
    def from_css(self) -> None:
        """Move presentation properties out of ``style`` into attributes."""
        style = self.style
        for name, value in style.presentation_only().items():
            self.attributes[name] = value
            del style[name]
        self.style = style


class XLinkAttributes(Element):
    """``xlink:href`` and the other XLink attributes."""

    def __init__(
        self,
        *args: Child,
        href: str | Element | None = None,
        xlink_title: str | None = None,
        xlink_show: str | None = None,
        xlink_actuate: str | None = None,
        xlink_role: str | None = None,
        xlink_arcrole: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.update(
            xlink_href=href,
            xlink_title=xlink_title,
            xlink_show=xlink_show,
            xlink_actuate=xlink_actuate,
            xlink_role=xlink_role,
            xlink_arcrole=xlink_arcrole,
        )

    @property
    def target(self) -> str | None:
        """The referenced id for local ``#id`` links."""
        raw = self.attributes.get("xlink:href")
        text = None if raw is None else str(raw)
        return text[1:] if text and text.startswith("#") else None


class ExternalResourcesAttribute(Element):
    def __init__(self, *args: Child, external_resources_required: bool | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.update(external_resources_required=external_resources_required)


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


class GraphicsElement(
    Transformable,
    ExternalResourcesAttribute,
    PresentationAttributes,
    ConditionalAttributes,
    CoreAttributes,
):
    """Rendered element carrying every common attribute group."""
