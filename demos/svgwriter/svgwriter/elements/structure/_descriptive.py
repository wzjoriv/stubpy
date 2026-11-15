"""``desc``, ``title`` and ``metadata``."""

from __future__ import annotations

from typing import Any

from .._mixins import CoreAttributes, StyleAttributes
from ..base import Category, Child, ContentModel

__all__ = ["Desc", "Metadata", "Title"]


class _Descriptive(StyleAttributes, CoreAttributes, category=Category.DESCRIPTIVE, content=ContentModel.TEXT):
    def __init__(self, text: str = "", **kwargs: Any) -> None:
        super().__init__(*([text] if text else []), **kwargs)


class Desc(_Descriptive, tag="desc"):
    """``<desc>``: a long description."""


class Title(_Descriptive, tag="title"):
    """``<title>``: a short, tooltip-style description."""


class Metadata(CoreAttributes, tag="metadata", category=Category.DESCRIPTIVE, content=ContentModel.MIXED):
    """``<metadata>``: arbitrary content, usually RDF in a foreign namespace."""

    def __init__(self, *children: Child, **kwargs: Any) -> None:
        super().__init__(*children, **kwargs)
