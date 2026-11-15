"""SVG fonts: ``font``, glyphs, kerning and ``font-face``."""

from __future__ import annotations

from typing import Any

from .._internal._typing import Self
from ..path.builder import PathBuilder
from ..path.data import PathData
from ._mixins import CoreAttributes, ExternalResourcesAttribute, PresentationAttributes, XLinkAttributes
from .base import Category, Child, ContentModel, Element
from .container import Container

__all__ = [
    "Font",
    "FontFace",
    "FontFaceFormat",
    "FontFaceName",
    "FontFaceSrc",
    "FontFaceUri",
    "Glyph",
    "HKern",
    "MissingGlyph",
    "VKern",
]


class Font(PresentationAttributes, ExternalResourcesAttribute, CoreAttributes, Container[Element], tag="font", category=Category.FONT):
    """``<font>``: an SVG font made of glyph outlines.

    Parameters
    ----------
    horiz_adv_x : float
        Default horizontal advance of glyphs.
    **kwargs
        Origins and vertical metrics, presentation and core attributes.
    """

    def __init__(
        self,
        *children: Child,
        horiz_adv_x: float = 0,
        horiz_origin_x: float | None = None,
        horiz_origin_y: float | None = None,
        vert_origin_x: float | None = None,
        vert_origin_y: float | None = None,
        vert_adv_y: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.update(
            horiz_origin_x=horiz_origin_x,
            horiz_origin_y=horiz_origin_y,
            horiz_adv_x=horiz_adv_x,
            vert_origin_x=vert_origin_x,
            vert_origin_y=vert_origin_y,
            vert_adv_y=vert_adv_y,
        )

    def glyph(self, unicode: str, d: PathData | PathBuilder | str, **kwargs: Any) -> Glyph:
        """Append a glyph and return it."""
        return self.add(Glyph(unicode, d, **kwargs))

    def glyphs(self) -> dict[str, Glyph]:
        return {str(g.get("unicode")): g for g in self if isinstance(g, Glyph)}


class _GlyphBase(PresentationAttributes, CoreAttributes, Container[Element], category=Category.FONT):
    def __init__(
        self,
        *children: Child,
        d: PathData | PathBuilder | str | None = None,
        horiz_adv_x: float | None = None,
        vert_origin_x: float | None = None,
        vert_origin_y: float | None = None,
        vert_adv_y: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*children, **kwargs)
        if isinstance(d, PathBuilder):
            d = d.build()
        elif isinstance(d, str):
            d = PathData(d)
        self.update(d=d, horiz_adv_x=horiz_adv_x, vert_origin_x=vert_origin_x, vert_origin_y=vert_origin_y, vert_adv_y=vert_adv_y)


class Glyph(_GlyphBase, tag="glyph"):
    """``<glyph>``: the outline for one character sequence."""

    def __init__(
        self,
        unicode: str | None = None,
        d: PathData | PathBuilder | str | None = None,
        *,
        glyph_name: str | None = None,
        orientation: str | None = None,
        arabic_form: str | None = None,
        lang: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(d=d, **kwargs)
        self.update(unicode=unicode, glyph_name=glyph_name, orientation=orientation, arabic_form=arabic_form, lang=lang)


class MissingGlyph(_GlyphBase, tag="missing-glyph"):
    """``<missing-glyph>``: drawn for characters without a glyph."""


class _Kern(CoreAttributes, category=Category.FONT, content=ContentModel.EMPTY):
    def __init__(
        self,
        k: float,
        *,
        u1: str | None = None,
        g1: str | None = None,
        u2: str | None = None,
        g2: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.update(u1=u1, g1=g1, u2=u2, g2=g2, k=k)

    @classmethod
    def pair(cls, first: str, second: str, k: float, **kwargs: Any) -> Self:
        """Kern a pair of characters by Unicode."""
        return cls(k, u1=first, u2=second, **kwargs)


class HKern(_Kern, tag="hkern"):
    """``<hkern>``: horizontal kerning pair."""


class VKern(_Kern, tag="vkern"):
    """``<vkern>``: vertical kerning pair."""


class FontFace(CoreAttributes, Container[Element], tag="font-face", category=Category.FONT):
    """``<font-face>``: font descriptors, mirroring CSS ``@font-face``.

    Less common descriptors (``panose_1``, ``v_alphabetic``,
    ``underline_position`` and so on) go through ``**descriptors``.
    """

    def __init__(
        self,
        *children: Child,
        font_family: str | None = None,
        font_style: str | None = None,
        font_variant: str | None = None,
        font_weight: str | None = None,
        font_stretch: str | None = None,
        font_size: str | None = None,
        unicode_range: str | None = None,
        units_per_em: float | None = None,
        ascent: float | None = None,
        descent: float | None = None,
        cap_height: float | None = None,
        x_height: float | None = None,
        **descriptors: Any,
    ) -> None:
        super().__init__(*children, **descriptors)
        self.update(
            font_family=font_family,
            font_style=font_style,
            font_variant=font_variant,
            font_weight=font_weight,
            font_stretch=font_stretch,
            font_size=font_size,
            unicode_range=unicode_range,
            units_per_em=units_per_em,
            ascent=ascent,
            descent=descent,
            cap_height=cap_height,
            x_height=x_height,
        )


class FontFaceSrc(CoreAttributes, Container[Element], tag="font-face-src", category=Category.FONT):
    """``<font-face-src>``: where the font data comes from."""


class FontFaceFormat(CoreAttributes, tag="font-face-format", category=Category.FONT, content=ContentModel.EMPTY):
    """``<font-face-format>``: the format of a ``font-face-uri``."""

    def __init__(self, string: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(string=string)


class FontFaceUri(XLinkAttributes, CoreAttributes, Container[FontFaceFormat], tag="font-face-uri", category=Category.FONT):
    """``<font-face-uri>``: an external font reference."""

    def __init__(self, href: str | None = None, *formats: FontFaceFormat, **kwargs: Any) -> None:
        super().__init__(*formats, href=href, **kwargs)


class FontFaceName(CoreAttributes, tag="font-face-name", category=Category.FONT, content=ContentModel.EMPTY):
    """``<font-face-name>``: a locally installed font by name."""

    def __init__(self, name: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update(name=name)
