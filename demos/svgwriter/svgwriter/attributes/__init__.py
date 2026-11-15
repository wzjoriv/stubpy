"""Attribute value types: lengths, view boxes, styles, references, names."""

from __future__ import annotations

from .descriptors import Attr
from .length import Length, LengthLike, Unit, cm, em, ex, inch, mm, pc, percent, pt, px
from .names import CAMEL_CASE_ATTRIBUTES, PRESENTATION_ATTRIBUTES, py_name, svg_name
from .protocols import SupportsSVG, TextSink
from .reference import IRI, FuncIRI, parse_func_iri
from .style import Style, StyleLike, StyleSheet
from .values import format_value
from .viewbox import Align, MeetOrSlice, PreserveAspectRatio, ViewBox

__all__ = [
    "CAMEL_CASE_ATTRIBUTES",
    "IRI",
    "PRESENTATION_ATTRIBUTES",
    "Align",
    "Attr",
    "FuncIRI",
    "Length",
    "LengthLike",
    "MeetOrSlice",
    "PreserveAspectRatio",
    "Style",
    "StyleLike",
    "StyleSheet",
    "SupportsSVG",
    "TextSink",
    "Unit",
    "ViewBox",
    "cm",
    "em",
    "ex",
    "format_value",
    "inch",
    "mm",
    "pc",
    "parse_func_iri",
    "percent",
    "pt",
    "px",
    "py_name",
    "svg_name",
]
