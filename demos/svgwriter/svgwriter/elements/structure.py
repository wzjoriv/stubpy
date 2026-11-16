"""``svg``, ``g``, ``defs`` and ``use``."""

from __future__ import annotations

from typing import Any

from .._internal._typing import Self
from ..attributes.length import LengthLike
from ._mixins import CoreAttributes, GraphicsElement, PresentationAttributes, XLinkAttributes
from .base import Category, Child, Element
from .container import GraphicsContainer

__all__ = ["Defs", "Group", "Svg", "Use"]

SVG_VERSION = "1.1"


class Svg(PresentationAttributes, CoreAttributes, GraphicsContainer, tag="svg", category=Category.STRUCTURAL):
    """``<svg>``: a document root or nested viewport."""

    def __init__(self, *children: Child, version: str | None = SVG_VERSION, **kwargs: Any) -> None:
        super().__init__(*children, **kwargs)
        self.update(version=version)

    @classmethod
    def with_size(cls, width: float, height: float, **kwargs: Any) -> Self:
        """A root sized ``width`` x ``height`` with a matching viewBox."""
        kwargs.setdefault("view_box", (0, 0, width, height))
        return cls(width=width, height=height, **kwargs)

    def defs(self) -> Defs:
        """The first ``<defs>`` child, created on demand."""
        for child in self:
            if isinstance(child, Defs):
                return child
        return self.insert(0, Defs())


class Group(GraphicsElement, GraphicsContainer, tag="g", category=Category.CONTAINER):
    """``<g>``: groups elements to share attributes and a transform."""


class Defs(GraphicsElement, GraphicsContainer, tag="defs", category=Category.CONTAINER):
    """``<defs>``: referenced, never directly rendered, content."""


class Use(GraphicsElement, XLinkAttributes, tag="use", category=Category.STRUCTURAL):
    """``<use>``: renders a referenced element."""

    def __init__(self, href: str | Element | None = None, x: LengthLike | None = None, y: LengthLike | None = None, **kwargs: Any) -> None:
        super().__init__(href=href, x=x, y=y, **kwargs)

    @classmethod
    def of(cls, element: Element, **kwargs: Any) -> Self:
        """Reference *element*, giving it an id if it has none."""
        return cls(element, **kwargs)
