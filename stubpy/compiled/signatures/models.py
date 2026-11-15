"""Parsed signature model."""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from ..._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS

__all__ = ["Param", "Signature"]


@dataclass(frozen=True)
class Param:
    """One parameter: name, kind, annotation text and default text (``...`` when unknown)."""

    name: str
    kind: inspect._ParameterKind = POS_KW
    annotation: str | None = None
    default: str | None = None


@dataclass(frozen=True)
class Signature:
    """A parsed signature."""

    params: tuple[Param, ...]
    returns: str | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def is_generic(self) -> bool:
        """True for the uninformative ``(*args, **kwargs)`` placeholder."""
        kinds = [p.kind for p in self.params if p.name not in ("self", "cls")]
        return kinds == [VAR_POS, VAR_KW]

    def render(self) -> str:
        """The signature as stub text, ``(a: int, /, *, b: str = ...) -> float``."""
        parts: list[str] = []
        prev = None
        star_done = False
        for p in self.params:
            if prev == POS_ONLY and p.kind != POS_ONLY:
                parts.append("/")
            if p.kind == KW_ONLY and not star_done:
                parts.append("*")
                star_done = True
            if p.kind == VAR_POS:
                star_done = True
            prefix = "*" if p.kind == VAR_POS else "**" if p.kind == VAR_KW else ""
            text = prefix + p.name
            if p.annotation:
                text += f": {p.annotation}"
            if p.default is not None:
                text += f" = {p.default}" if p.annotation else f"={p.default}"
            parts.append(text)
            prev = p.kind
        if prev == POS_ONLY:
            parts.append("/")
        ret = f" -> {self.returns}" if self.returns else ""
        return f"({', '.join(parts)}){ret}"
