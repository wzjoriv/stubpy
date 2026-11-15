"""IRI references: ``#id`` and ``url(#id)``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .._internal._constants import DEFAULT_PRECISION

__all__ = ["IRI", "FuncIRI", "parse_func_iri"]

_FUNC_IRI_RE: Final = re.compile(r"""^\s*url\(\s*(['"]?)(.*?)\1\s*\)\s*$""")


@dataclass(frozen=True)
class IRI:
    """A plain IRI, local (``#id``) or external."""

    target: str

    @classmethod
    def local(cls, element_id: str) -> IRI:
        return cls("#" + element_id)

    @property
    def fragment(self) -> str | None:
        _, sep, fragment = self.target.partition("#")
        return fragment if sep else None

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return self.target

    def __str__(self) -> str:
        return self.svg_value()


@dataclass(frozen=True)
class FuncIRI(IRI):
    """A functional IRI, ``url(...)``, as used by paint and filter."""

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        return f"url({self.target})"


def parse_func_iri(text: str) -> FuncIRI | None:
    """Return the ``FuncIRI`` in *text*, or ``None`` when it is not one."""
    match = _FUNC_IRI_RE.match(text)
    return FuncIRI(match.group(2)) if match else None
