"""Elements without a dedicated class."""

from __future__ import annotations

from typing import Any

from .base import Child, Element
from ._categories import ContentModel

__all__ = ["UnknownElement"]


class UnknownElement(Element, content=ContentModel.MIXED):
    """An element without a dedicated class (foreign or unsupported)."""

    def __init__(self, tag: str, *children: Child, namespace: str | None = None, **kwargs: Any) -> None:
        super().__init__(*children, **kwargs)
        self.tag = tag  # type: ignore[misc]
        self.namespace = namespace
