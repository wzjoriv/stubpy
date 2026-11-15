"""Every SVG 1.1 element as a class.

Sub-packages and modules
------------------------
unknown     fallback for foreign or unsupported elements
structure   svg, g, defs, symbol, use, switch, a, desc, title, metadata,
            image, style, view, color-profile
shapes      rect, circle, ellipse, line, polyline, polygon, path
_geometry   ``PathOperand``: path conversion and geometric operators
_factory    ``ElementFactory``: ``doc.circle(...)``-style shortcuts
container   typed child lists, ``+=``, ``%`` and ``with`` nesting
text        text, tspan, tref, textPath, altGlyph, altGlyphDef, altGlyphItem, glyphRef
fonts       font, glyph, missing-glyph, hkern, vkern, font-face and children
paint       linearGradient, radialGradient, stop, pattern
clip        clipPath, mask, marker
filters     filter and all fe* primitives and light sources
animation   animate, set, animateMotion, mpath, animateColor, animateTransform
"""

from __future__ import annotations

from ._factory import ElementFactory
from ._geometry import PathOperand
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
from .container import Container, GraphicsContainer
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
    Defs,
    Desc,
    Group,
    Image,
    Metadata,
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
    "Defs",
    "Desc",
    "Element",
    "ElementFactory",
    "Ellipse",
    "ExternalResourcesAttribute",
    "FitToViewBox",
    "Font",
    "FontFace",
    "FontFaceFormat",
    "FontFaceName",
    "FontFaceSrc",
    "FontFaceUri",
    "Glyph",
    "GlyphRef",
    "Gradient",
    "GraphicsContainer",
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
    "PathOperand",
    "Pattern",
    "Polygon",
    "Polyline",
    "Positioned",
    "PresentationAttributes",
    "RadialGradient",
    "Rect",
    "Restart",
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
