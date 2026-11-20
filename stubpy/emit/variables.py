"""
Module-level variable stubs.
"""
from __future__ import annotations

import functools

from stubpy.analysis.symbols.models import FunctionSymbol, OverloadGroup, VariableSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage

from .annotations.private_aliases import inline_private_aliases
from .annotations.style import style_text
from .partials import generate_partial_stub, generate_static_partial_stub, partial_annotation


def generate_variable_stub(sym: VariableSymbol, ctx: StubContext) -> str:
    """Generate a ``name: Type`` line for a module-level variable.

    Uses the source annotation, else the inferred type (noted as an INFO
    diagnostic).  ``name = func`` re-binding a function of the module stays
    an assignment; an untyped name another module of the run imports becomes
    ``Incomplete``; anything else untyped returns ``""``.  A bare ``Final``
    keeps an ``= ...`` initializer, which it needs to be valid. A ``functools.partial``
    becomes a ``def`` with the parameters left open (``partial[T]`` without a
    live module).

    Parameters
    ----------
    sym : VariableSymbol
        The variable symbol.
    ctx : StubContext
        The current run context.

    Returns
    -------
    str
        The stub line, or ``""``.

    See Also
    --------
    generate_partial_stub : Writes the ``def`` for a partial.

    Examples
    --------
    >>> generate_variable_stub(VariableSymbol("MAX", 1, annotation_str="int"), StubContext())
    'MAX: int'
    """
    if isinstance(sym.live_value, functools.partial):
        return generate_partial_stub(sym.name, sym.live_value, ctx)
    raw = inline_private_aliases(sym.annotation_str, ctx.module_namespace, ctx) if sym.annotation_str else None
    type_str = style_text(raw, ctx) or None
    if type_str is not None and type_str.rpartition(".")[2] == "Final":
        return f"{sym.name}: {type_str} = ..."
    if type_str is None and sym.live_value is None and sym.ast_info is not None:
        type_str = partial_annotation(sym.ast_info.value_repr)
        if type_str is not None:
            stub = generate_static_partial_stub(sym.name, sym.ast_info.value_repr or "", ctx)
            if stub is not None:
                return stub

    if type_str is None:
        if sym.inferred_type_str:
            type_str = sym.inferred_type_str
            ctx.diagnostics.info(
                Stage.EMIT,
                sym.name,
                f"Inferred type {type_str!r} for {sym.name!r} from"
                f" {'literal default' if sym.live_value is None else 'runtime value'}.",
            )
        elif (target := _rebound_function(sym, ctx)) is not None:
            return f"{sym.name} = {target}"
        elif sym.name in ctx.requested_names:
            type_str = "Incomplete"
            ctx.extra_imports.setdefault("Incomplete", "from _typeshed import Incomplete")
        else:
            ctx.diagnostics.info(
                Stage.EMIT,
                sym.name,
                f"No annotation and no inferrable type for {sym.name!r}; omitting from stub.",
            )
            return ""

    return f"{sym.name}: {type_str}"


def _rebound_function(sym: VariableSymbol, ctx: StubContext) -> str | None:
    """The module function a bare ``name = func`` assignment re-binds, or ``None``."""
    value = sym.ast_info.value_repr if sym.ast_info is not None else None
    if not value or not value.isidentifier() or ctx.symbol_table is None:
        return None
    found = ctx.symbol_table.get(value, hidden=True)
    return value if isinstance(found, (FunctionSymbol, OverloadGroup)) else None
