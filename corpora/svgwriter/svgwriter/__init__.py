"""svgwriter: a small SVG writer, kept as a stubpy test corpus.

Every element is a class with keyword arguments for its attributes
(``stroke_width`` becomes ``stroke-width``), also available under a
lowercase alias (``svg.circle is svg.Circle``). Documents and containers
have shortcut methods that build, add and return elements.

>>> import svgwriter as svg
>>> doc = svg.Document(120, 80)
>>> grad = doc % svg.LinearGradient.horizontal("gold", "tomato")
>>> with doc.group(stroke="black", stroke_width=2) as g:
...     _ = doc.rect(10, 10, 100, 60, fill=grad)
>>> g += svg.circle(60, 40, 3)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .attributes import IRI, FuncIRI, Length, Unit, cm, em, inch, mm, percent, pt, px
from .color import Color, PaintKeyword, parse_color, parse_paint
from . import ops
from .document import Document, ShapeKind
from .elements import *  # noqa: F403
from .elements import __all__ as _elements_all
from .io.writer import SerializeOptions, to_string, write
from .ops import MissingDependencyError
from .path import BBox, PathBuilder, PathData
from .transform import Matrix, Point, Transform

from .aliases import *  # noqa: E402, F403  (after the sub-packages: ``path`` names the class)
from .aliases import __all__ as _aliases_all  # noqa: E402
from .aliases import filter as filter, set as set  # noqa: A004, E402

if TYPE_CHECKING:
    from .io._async import write_async

__version__ = "1.1.0"

_LAZY = {"write_async": ("io._async", "write_async")}


def __getattr__(name: str) -> Any:
    """Import the async helpers on first use."""
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
    "Color",
    "Document",
    "FuncIRI",
    "IRI",
    "Length",
    "Matrix",
    "MissingDependencyError",
    "PaintKeyword",
    "PathBuilder",
    "PathData",
    "Point",
    "SerializeOptions",
    "ShapeKind",
    "Transform",
    "Unit",
    "__version__",
    "cm",
    "em",
    "inch",
    "mm",
    "ops",
    "parse_color",
    "parse_paint",
    "percent",
    "pt",
    "px",
    "to_string",
    "write",
    "write_async",
    *_elements_all,
    *_aliases_all,
]
