"""The element classes.

Sub-packages and modules
------------------------
structure   svg, g, defs, use
shapes      rect, circle, line, path
_geometry   ``PathOperand``: path conversion and geometric operators
_factory    ``ElementFactory``: ``doc.circle(...)``-style shortcuts
container   typed child lists, ``+=``, ``%`` and ``with`` nesting
effects     gradients, filters and animation
"""

from __future__ import annotations

from ._factory import ElementFactory
from ._geometry import PathOperand
from ._mixins import (
    CoreAttributes,
    GraphicsElement,
    PresentationAttributes,
    StyleAttributes,
    Transformable,
    XLinkAttributes,
)
from .base import AttrValue, Category, Child, ContentModel, Element
from .container import Container, GraphicsContainer
from .effects import Animate, FeGaussianBlur, Filter, LinearGradient, Set, Stop
from .shapes import Circle, Line, Path, Rect, Shape
from .structure import Defs, Group, Svg, Use

__all__ = [
    "Animate",
    "AttrValue",
    "Category",
    "Child",
    "Circle",
    "Container",
    "ContentModel",
    "CoreAttributes",
    "Defs",
    "Element",
    "ElementFactory",
    "FeGaussianBlur",
    "Filter",
    "GraphicsContainer",
    "GraphicsElement",
    "Group",
    "Line",
    "LinearGradient",
    "Path",
    "PathOperand",
    "PresentationAttributes",
    "Rect",
    "Set",
    "Shape",
    "Stop",
    "StyleAttributes",
    "Svg",
    "Transformable",
    "Use",
    "XLinkAttributes",
]
