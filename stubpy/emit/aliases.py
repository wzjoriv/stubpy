"""TypeVar, TypeAlias, NewType, ParamSpec and TypeVarTuple declaration stubs."""
from __future__ import annotations

import sys

from stubpy.analysis.symbols.models import AliasSymbol
from stubpy.core.context import StubContext

from .annotations.style import style_text


def resolve_alias_style(ctx: StubContext) -> str:
    """Return the effective alias style, ``"pep695"`` or ``"compatible"``."""
    style = getattr(ctx.config, "alias_style", "compatible")
    if style == "auto":
        return "pep695" if sys.version_info >= (3, 12) else "compatible"
    return style if style in ("pep695", "compatible") else "compatible"


def generate_alias_stub(sym: AliasSymbol, ctx: StubContext) -> str:
    """Re-emit a type alias or TypeVar-style declaration from its source text.

    Type aliases follow ``alias_style``: ``Name: TypeAlias = rhs``
    (compatible) or ``type Name = rhs`` (pep695); a generic PEP 695 alias
    (``type Pair[T] = ...``) keeps its own syntax, which its source already needs.  TypeVar, ParamSpec,
    TypeVarTuple and NewType always emit ``Name = Kind(...)``.

    Parameters
    ----------
    sym : AliasSymbol
        The alias symbol.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        One declaration line, or ``""`` without AST data.

    Examples
    --------
    >>> from stubpy.analysis.harvest import TypeVarInfo
    >>> tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
    >>> generate_alias_stub(AliasSymbol("T", lineno=1, ast_info=tv), StubContext())
    "T = TypeVar('T')"
    """
    ai = sym.ast_info
    if ai is None:
        return ""

    if ai.kind == "TypeAlias":
        rhs = style_text(ai.source_str, ctx)
        if ai.type_params:
            return f"type {sym.name}[{', '.join(ai.type_params)}] = {rhs}"
        if resolve_alias_style(ctx) == "pep695":
            return f"type {sym.name} = {rhs}" if rhs else f"type {sym.name}"
        if rhs:
            return f"{sym.name}: TypeAlias = {rhs}"
        return f"{sym.name}: TypeAlias"

    if ai.source_str:
        return f"{sym.name} = {ai.source_str}"
    return ""
