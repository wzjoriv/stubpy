"""Structural protocols used by attribute serialization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["SupportsSVG", "TextSink"]


@runtime_checkable
class SupportsSVG(Protocol):
    """Anything that knows how to render itself as an attribute value."""

    def svg_value(self, precision: int = ...) -> str: ...


@runtime_checkable
class TextSink(Protocol):
    """A writable text stream."""

    def write(self, text: str, /) -> object: ...
