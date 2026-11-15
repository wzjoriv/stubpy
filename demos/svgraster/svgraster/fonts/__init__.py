"""TrueType/OpenType and SVG fonts: parsing, discovery and matching.

Usage::

    from svgraster.fonts import Font, default_database

    face = Font.from_file("C:/Windows/Fonts/arial.ttf")
    face.text_width("Hello", size=16)
    best = default_database().match("Georgia, serif", weight="bold")[0].font
"""
from ._reader import FontFormatError
from ._scan import FaceInfo, system_font_dirs
from .database import FontDatabase, FontMatch, add_font_path, default_database, parse_family_list, weight_value
from .font import Font, font_faces
from .svgfont import SvgFont

__all__ = [
    "FaceInfo",
    "Font",
    "FontDatabase",
    "FontFormatError",
    "FontMatch",
    "SvgFont",
    "add_font_path",
    "default_database",
    "font_faces",
    "parse_family_list",
    "system_font_dirs",
    "weight_value",
]
