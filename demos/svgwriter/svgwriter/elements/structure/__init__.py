"""Structural, descriptive and external-content elements."""

from __future__ import annotations

from ._containers import A, Defs, Group, Svg, Switch, Symbol, Use
from ._descriptive import Desc, Metadata, Title
from ._external import ColorProfile, Cursor, ForeignObject, Image, Script, StyleElement, View

__all__ = [
    "A",
    "ColorProfile",
    "Cursor",
    "Defs",
    "Desc",
    "ForeignObject",
    "Group",
    "Image",
    "Metadata",
    "Script",
    "StyleElement",
    "Svg",
    "Switch",
    "Symbol",
    "Title",
    "Use",
    "View",
]
