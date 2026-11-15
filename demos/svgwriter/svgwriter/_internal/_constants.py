"""Namespaces, defaults and unit conversion factors."""

from __future__ import annotations

from typing import Final

__all__ = [
    "BASE_PROFILE",
    "CM_PER_INCH",
    "DEFAULT_DPI",
    "DEFAULT_FONT_SIZE",
    "DEFAULT_INDENT",
    "DEFAULT_PRECISION",
    "DOCTYPE",
    "EX_PER_EM",
    "INDEFINITE",
    "MM_PER_INCH",
    "PC_PER_INCH",
    "PT_PER_INCH",
    "SVG_NS",
    "SVG_VERSION",
    "XLINK_NS",
    "XML_NS",
]

SVG_NS: Final = "http://www.w3.org/2000/svg"
XLINK_NS: Final = "http://www.w3.org/1999/xlink"
XML_NS: Final = "http://www.w3.org/XML/1998/namespace"

SVG_VERSION: Final = "1.1"
BASE_PROFILE: Final = "full"
DOCTYPE: Final = (
    '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
    '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
)

DEFAULT_PRECISION: Final = 4
DEFAULT_INDENT: Final = "  "
INDEFINITE: Final = "indefinite"

DEFAULT_DPI: Final = 96.0
DEFAULT_FONT_SIZE: Final = 16.0
EX_PER_EM: Final = 0.5
PT_PER_INCH: Final = 72.0
PC_PER_INCH: Final = 6.0
MM_PER_INCH: Final = 25.4
CM_PER_INCH: Final = 2.54
