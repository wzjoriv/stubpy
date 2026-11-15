"""Every SVG 1.1 element as a class.

Sub-packages and modules
------------------------
unknown     fallback for foreign or unsupported elements
structure   svg, g, defs, symbol, use, switch, a, desc, title, metadata,
            image, style, script, foreignObject, view, cursor, color-profile
shapes      rect, circle, ellipse, line, polyline, polygon, path
text        text, tspan, tref, textPath, altGlyph, altGlyphDef, altGlyphItem, glyphRef
fonts       font, glyph, missing-glyph, hkern, vkern, font-face and children
paint       linearGradient, radialGradient, stop, pattern
clip        clipPath, mask, marker
filters     filter and all fe* primitives and light sources
animation   animate, set, animateMotion, mpath, animateColor, animateTransform
"""

from __future__ import annotations

from ._mixins import (
    ConditionalAttributes,
    CoreAttributes,
    ExternalResourcesAttribute,
    GraphicsElement,
    PresentationAttributes,
    StyleAttributes,
    Transformable,
    XLinkAttributes,
    XmlSpace,
)
from ._viewport import FitToViewBox, Positioned
from .animation import (
    Accumulate,
    Additive,
    Animate,
    AnimateColor,
    AnimateMotion,
    AnimateTransform,
    AnimationElement,
    AnimationFill,
    CalcMode,
    MPath,
    Restart,
    Set,
    TransformType,
)
from .base import AttrValue, Category, Child, ContentModel, Element
from .clip import ClipPath, Marker, Mask
from .container import Container
from .filters import *  # noqa: F403
from .filters import __all__ as _filters_all
from .fonts import (
    Font,
    FontFace,
    FontFaceFormat,
    FontFaceName,
    FontFaceSrc,
    FontFaceUri,
    Glyph,
    HKern,
    MissingGlyph,
    VKern,
)
from .paint import Gradient, LinearGradient, Pattern, RadialGradient, Stop
from .shapes import Circle, Ellipse, Line, Path, Polygon, Polyline, Rect, Shape
from .structure import (
    A,
    ColorProfile,
    Cursor,
    Defs,
    Desc,
    ForeignObject,
    Group,
    Image,
    Metadata,
    Script,
    StyleElement,
    Svg,
    Switch,
    Symbol,
    Title,
    Use,
    View,
)
from .text import AltGlyph, AltGlyphDef, AltGlyphItem, GlyphRef, Text, TextDecoration, TextPath, TRef, TSpan
from .unknown import UnknownElement

__all__ = [
    "A",
    "Accumulate",
    "Additive",
    "AltGlyph",
    "AltGlyphDef",
    "AltGlyphItem",
    "Animate",
    "AnimateColor",
    "AnimateMotion",
    "AnimateTransform",
    "AnimationElement",
    "AnimationFill",
    "AttrValue",
    "CalcMode",
    "Category",
    "Child",
    "Circle",
    "ClipPath",
    "ColorProfile",
    "ConditionalAttributes",
    "Container",
    "ContentModel",
    "CoreAttributes",
    "Cursor",
    "Defs",
    "Desc",
    "Element",
    "Ellipse",
    "ExternalResourcesAttribute",
    "FitToViewBox",
    "Font",
    "FontFace",
    "FontFaceFormat",
    "FontFaceName",
    "FontFaceSrc",
    "FontFaceUri",
    "ForeignObject",
    "Glyph",
    "GlyphRef",
    "Gradient",
    "GraphicsElement",
    "Group",
    "HKern",
    "Image",
    "Line",
    "LinearGradient",
    "MPath",
    "Marker",
    "Mask",
    "Metadata",
    "MissingGlyph",
    "Path",
    "Pattern",
    "Polygon",
    "Polyline",
    "Positioned",
    "PresentationAttributes",
    "RadialGradient",
    "Rect",
    "Restart",
    "Script",
    "Set",
    "Shape",
    "Stop",
    "StyleAttributes",
    "StyleElement",
    "Svg",
    "Switch",
    "Symbol",
    "TRef",
    "TSpan",
    "Text",
    "TextDecoration",
    "TextPath",
    "Title",
    "TransformType",
    "Transformable",
    "UnknownElement",
    "Use",
    "VKern",
    "View",
    "XLinkAttributes",
    "XmlSpace",
    *_filters_all,
]
