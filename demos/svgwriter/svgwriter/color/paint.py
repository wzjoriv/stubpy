"""The ``<paint>`` type used by ``fill`` and ``stroke``."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, Union

from .._internal._constants import DEFAULT_PRECISION
from ..attributes.reference import FuncIRI, parse_func_iri
from .color import Color, parse_color

if TYPE_CHECKING:
    from ..elements.base import Element

__all__ = ["Paint", "PaintKeyword", "PaintRef", "PaintValue", "parse_paint"]


class PaintKeyword(str, enum.Enum):
    NONE = "none"
    CURRENT_COLOR = "currentColor"
    INHERIT = "inherit"


@dataclass(frozen=True)
class PaintRef:
    """A paint server reference with an optional fallback."""

    iri: FuncIRI
    fallback: Color | PaintKeyword | None = None

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        text = self.iri.svg_value(precision)
        if self.fallback is not None:
            text += " " + (self.fallback.value if isinstance(self.fallback, PaintKeyword) else self.fallback.svg_value(precision))
        return text

    def __str__(self) -> str:
        return self.svg_value()


Paint: TypeAlias = Color | PaintKeyword | PaintRef
PaintValue: TypeAlias = Union[Paint, str, "Element", None]


def parse_paint(text: str) -> Paint:
    """Parse a ``fill`` or ``stroke`` value."""
    source = text.strip()
    for keyword in PaintKeyword:
        if source == keyword.value:
            return keyword
    if source.startswith("url("):
        end = source.index(")") + 1
        iri = parse_func_iri(source[:end])
        if iri is None:
            raise ValueError(f"invalid paint reference: {text!r}")
        rest = source[end:].strip()
        fallback: Color | PaintKeyword | None = None
        if rest:
            parsed = parse_paint(rest)
            if isinstance(parsed, PaintRef):
                raise ValueError("a paint fallback cannot be another reference")
            fallback = parsed
        return PaintRef(iri, fallback)
    return parse_color(source)
