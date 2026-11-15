"""svgwriter: write SVG 1.1 documents from Python.

Every SVG 1.1 element is a class with keyword arguments for its attributes
(``stroke_width`` becomes ``stroke-width``, ``class_`` becomes ``class``).
Documents serialize to pretty or compact text and parse back into the same
object model.

Example
-------
>>> import svgwriter as svg
>>> doc = svg.Document(120, 80)
>>> grad = doc.define(svg.LinearGradient.horizontal("gold", "tomato"))
>>> with doc.group(stroke="black", stroke_width=2) as g:
...     _ = doc.add(svg.Rect(10, 10, 100, 60, rx=8, fill=grad))
...     _ = doc.add(svg.Text("Hello", x=60, y=45, text_anchor="middle"))
>>> text = doc.to_string()
>>> svg.parse(text).find(svg.Rect).get("rx")
'8'

Sub-packages
------------
elements
    One class per SVG element (``structure``, ``shapes``, ``text``,
    ``fonts``, ``paint``, ``clip``, ``filters``, ``animation``).
attributes
    Lengths and units, ``viewBox``, ``preserveAspectRatio``, inline styles
    and style sheets, IRI references, attribute-name mapping.
path
    Path commands, parsing, serialization, arc math and ``PathBuilder``.
transform
    Affine matrices and transform lists.
color
    Color keywords and syntaxes and the ``<paint>`` type.
io
    Serialization options, writers (string, file, stream, async) and the
    parser.
builder
    Lowercase functional constructors, composite shapes and effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .attributes import (
    IRI,
    Align,
    FuncIRI,
    Length,
    MeetOrSlice,
    PreserveAspectRatio,
    Style,
    StyleSheet,
    Unit,
    ViewBox,
    cm,
    em,
    inch,
    mm,
    percent,
    pt,
    px,
)
from .builder import SHAPES, drawing, drop_shadow, shape_factory
from .color import Color, PaintKeyword, parse_color, parse_paint
from .document import Document, ShapeKind
from .elements import *  # noqa: F403
from .elements import __all__ as _elements_all
from .io.writer import SerializeOptions, to_string, write
from .path import PathBuilder, PathData
from .transform import Matrix, Transform

if TYPE_CHECKING:
    from .io._async import write_async
    from .io.parser import Strictness, parse, parse_file

__version__ = "1.0.0"
__author__ = "Josue N Rivera"

_LAZY = {
    "parse": ("io.parser", "parse"),
    "parse_file": ("io.parser", "parse_file"),
    "Strictness": ("io.parser", "Strictness"),
    "write_async": ("io._async", "write_async"),
}


def __getattr__(name: str) -> Any:
    """Import the parser and async helpers on first use."""
    if name in _LAZY:
        import importlib

        module_name, attribute = _LAZY[name]
        value = getattr(importlib.import_module(f".{module_name}", __name__), attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "IRI",
    "SHAPES",
    "Align",
    "Color",
    "Document",
    "FuncIRI",
    "Length",
    "Matrix",
    "MeetOrSlice",
    "PaintKeyword",
    "PathBuilder",
    "PathData",
    "PreserveAspectRatio",
    "SerializeOptions",
    "ShapeKind",
    "Strictness",
    "Style",
    "StyleSheet",
    "Transform",
    "Unit",
    "ViewBox",
    "__author__",
    "__version__",
    "cm",
    "drawing",
    "drop_shadow",
    "em",
    "inch",
    "mm",
    "parse",
    "parse_color",
    "parse_file",
    "parse_paint",
    "percent",
    "pt",
    "px",
    "shape_factory",
    "to_string",
    "write",
    "write_async",
    *_elements_all,
]
