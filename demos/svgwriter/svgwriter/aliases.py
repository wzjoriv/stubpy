"""Lowercase aliases for every element class.

``svg.circle`` is ``svg.Circle``, ``svg.linear_gradient`` is
``svg.LinearGradient`` and so on: the same class under the SVG-flavoured
snake_case spelling, for code that reads closer to the markup.

``filter`` and ``set`` shadow builtins, so they are attributes of the
package but left out of ``__all__``; ``from svgwriter import *`` will not
replace the builtins. ``svgwriter.path`` names the class, not the
``svgwriter.path`` sub-package; import from that with
``from svgwriter.path import PathBuilder``.

Examples
--------
>>> import svgwriter as svg
>>> svg.circle is svg.Circle
True
>>> str(svg.circle(5, 5, 2, fill="red"))
'<circle fill="red" cx="5" cy="5" r="2"/>'
"""

from __future__ import annotations

from .elements import (
    A,
    AltGlyph,
    AltGlyphDef,
    AltGlyphItem,
    Animate,
    AnimateColor,
    AnimateMotion,
    AnimateTransform,
    Circle,
    ClipPath,
    ColorProfile,
    Defs,
    Desc,
    Ellipse,
    FeBlend,
    FeColorMatrix,
    FeComponentTransfer,
    FeComposite,
    FeConvolveMatrix,
    FeDiffuseLighting,
    FeDisplacementMap,
    FeDistantLight,
    FeFlood,
    FeFuncA,
    FeFuncB,
    FeFuncG,
    FeFuncR,
    FeGaussianBlur,
    FeImage,
    FeMerge,
    FeMergeNode,
    FeMorphology,
    FeOffset,
    FePointLight,
    FeSpecularLighting,
    FeSpotLight,
    FeTile,
    FeTurbulence,
    Filter,
    Font,
    FontFace,
    FontFaceFormat,
    FontFaceName,
    FontFaceSrc,
    FontFaceUri,
    Glyph,
    GlyphRef,
    Group,
    HKern,
    Image,
    Line,
    LinearGradient,
    MPath,
    Marker,
    Mask,
    Metadata,
    MissingGlyph,
    Path,
    Pattern,
    Polygon,
    Polyline,
    RadialGradient,
    Rect,
    Set,
    Stop,
    StyleElement,
    Svg,
    Switch,
    Symbol,
    TRef,
    TSpan,
    Text,
    TextPath,
    Title,
    Use,
    VKern,
    View,
)

__all__ = [
    "a",
    "alt_glyph",
    "alt_glyph_def",
    "alt_glyph_item",
    "animate",
    "animate_color",
    "animate_motion",
    "animate_transform",
    "circle",
    "clip_path",
    "color_profile",
    "defs",
    "desc",
    "ellipse",
    "fe_blend",
    "fe_color_matrix",
    "fe_component_transfer",
    "fe_composite",
    "fe_convolve_matrix",
    "fe_diffuse_lighting",
    "fe_displacement_map",
    "fe_distant_light",
    "fe_flood",
    "fe_func_a",
    "fe_func_b",
    "fe_func_g",
    "fe_func_r",
    "fe_gaussian_blur",
    "fe_image",
    "fe_merge",
    "fe_merge_node",
    "fe_morphology",
    "fe_offset",
    "fe_point_light",
    "fe_specular_lighting",
    "fe_spot_light",
    "fe_tile",
    "fe_turbulence",
    "font",
    "font_face",
    "font_face_format",
    "font_face_name",
    "font_face_src",
    "font_face_uri",
    "glyph",
    "glyph_ref",
    "group",
    "hkern",
    "image",
    "line",
    "linear_gradient",
    "marker",
    "mask",
    "metadata",
    "missing_glyph",
    "mpath",
    "path",
    "pattern",
    "polygon",
    "polyline",
    "radial_gradient",
    "rect",
    "stop",
    "style_element",
    "svg",
    "switch",
    "symbol",
    "text",
    "text_path",
    "title",
    "tref",
    "tspan",
    "use",
    "view",
    "vkern",
]

a = A
alt_glyph = AltGlyph
alt_glyph_def = AltGlyphDef
alt_glyph_item = AltGlyphItem
animate = Animate
animate_color = AnimateColor
animate_motion = AnimateMotion
animate_transform = AnimateTransform
circle = Circle
clip_path = ClipPath
color_profile = ColorProfile
defs = Defs
desc = Desc
ellipse = Ellipse
fe_blend = FeBlend
fe_color_matrix = FeColorMatrix
fe_component_transfer = FeComponentTransfer
fe_composite = FeComposite
fe_convolve_matrix = FeConvolveMatrix
fe_diffuse_lighting = FeDiffuseLighting
fe_displacement_map = FeDisplacementMap
fe_distant_light = FeDistantLight
fe_flood = FeFlood
fe_func_a = FeFuncA
fe_func_b = FeFuncB
fe_func_g = FeFuncG
fe_func_r = FeFuncR
fe_gaussian_blur = FeGaussianBlur
fe_image = FeImage
fe_merge = FeMerge
fe_merge_node = FeMergeNode
fe_morphology = FeMorphology
fe_offset = FeOffset
fe_point_light = FePointLight
fe_specular_lighting = FeSpecularLighting
fe_spot_light = FeSpotLight
fe_tile = FeTile
fe_turbulence = FeTurbulence
filter = Filter
font = Font
font_face = FontFace
font_face_format = FontFaceFormat
font_face_name = FontFaceName
font_face_src = FontFaceSrc
font_face_uri = FontFaceUri
glyph = Glyph
glyph_ref = GlyphRef
group = Group
hkern = HKern
image = Image
line = Line
linear_gradient = LinearGradient
mpath = MPath
marker = Marker
mask = Mask
metadata = Metadata
missing_glyph = MissingGlyph
path = Path
pattern = Pattern
polygon = Polygon
polyline = Polyline
radial_gradient = RadialGradient
rect = Rect
set = Set
stop = Stop
style_element = StyleElement
svg = Svg
switch = Switch
symbol = Symbol
tref = TRef
tspan = TSpan
text = Text
text_path = TextPath
title = Title
use = Use
vkern = VKern
view = View
