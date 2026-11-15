"""svgwriter: write SVG 1.1 documents from Python.

Every SVG 1.1 element is a class with keyword arguments for its attributes
(``stroke_width`` becomes ``stroke-width``, ``class_`` becomes ``class``),
also available under a lowercase alias (``svg.circle is svg.Circle``).
Documents and containers have shortcut methods that build, add and return
elements; operators compose them. Documents serialize to pretty or compact
text and parse back into the same object model.

Example
-------
>>> import svgwriter as svg
>>> doc = svg.Document(120, 80)
>>> grad = doc % svg.LinearGradient.horizontal("gold", "tomato")
>>> with doc.group(stroke="black", stroke_width=2) as g:
...     _ = doc.rect(10, 10, 100, 60, rx=8, fill=grad)
...     _ = doc.text("Hello", x=60, y=45, text_anchor="middle")
>>> g += svg.circle(60, 40, 3)
>>> svg.parse(doc.to_string()).find(svg.Rect).get("rx")
'8'

Sub-packages
------------
elements
    One class per SVG 1.1 element (``structure``, ``shapes``, ``text``,
    ``fonts``, ``paint``, ``clip``, ``filters``, ``animation``).
attributes
    Lengths and units, ``viewBox``, ``preserveAspectRatio``, inline styles
    and style sheets, IRI references, attribute-name mapping.
path
    Path commands, parsing, serialization, transforms, arc math and
    ``PathBuilder``.
transform
    Affine matrices and transform lists.
color
    Color keywords and syntaxes and the ``<paint>`` type.
io
    Serialization options, writers (string, file, stream, async) and the
    parser.
builder
    Functional constructors, composite shapes and effects.
ops
    Boolean operations, text outlines and exact measurement, backed by the
    optional skia-python dependency (``pip install 'svgwriter[ops]'``).
video
    Frame rendering through a pluggable renderer and encoding with ffmpeg.
cli
    The ``python -m svgwriter`` command line.
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
from . import ops, video
from .document import Document, ShapeKind
from .elements import *  # noqa: F403
from .elements import __all__ as _elements_all
from .io.writer import SerializeOptions, to_string, write
from .ops import MissingDependencyError, text_to_path
from .path import BBox, PathBuilder, PathData
from .transform import Matrix, Point, Transform
from .video import FFmpegNotFoundError, register_renderer

from .aliases import *  # noqa: E402, F403  (after the sub-packages: ``path`` names the class)
from .aliases import __all__ as _aliases_all  # noqa: E402
from .aliases import filter as filter, set as set  # noqa: A004, E402

if TYPE_CHECKING:
    from .io._async import write_async
    from .io.parser import Strictness, SVGParseError, parse, parse_file

__version__ = "1.1.0"
__author__ = "Josue N Rivera"

_LAZY = {
    "parse": ("io.parser", "parse"),
    "parse_file": ("io.parser", "parse_file"),
    "Strictness": ("io.parser", "Strictness"),
    "SVGParseError": ("io.parser", "SVGParseError"),
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
    return sorted({*globals(), *_LAZY})


__all__ = [
    "BBox",
    "FFmpegNotFoundError",
    "IRI",
    "MissingDependencyError",
    "Point",
    "SVGParseError",
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
    "ops",
    "percent",
    "pt",
    "px",
    "register_renderer",
    "shape_factory",
    "text_to_path",
    "to_string",
    "video",
    "write",
    "write_async",
    *_elements_all,
    *_aliases_all,
]
