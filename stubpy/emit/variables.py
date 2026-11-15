"""Module-level variable stubs."""
from __future__ import annotations

import functools

from stubpy.analysis.symbols.models import VariableSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Stage

from .annotations.style import style_text
from .partials import generate_partial_stub, partial_annotation


def generate_variable_stub(sym: VariableSymbol, ctx: StubContext) -> str:
    """Generate a ``name: Type`` line for a module-level variable.

    Uses the source annotation, else the inferred type (noted as an INFO
    diagnostic); returns ``""`` when neither exists.  A ``functools.partial``
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

    Examples
    --------
    >>> generate_variable_stub(VariableSymbol("MAX", 1, annotation_str="int"), StubContext())
    'MAX: int'
    """
    if isinstance(sym.live_value, functools.partial):
        return generate_partial_stub(sym.name, sym.live_value, ctx)
    type_str = style_text(sym.annotation_str, ctx) or None
    if type_str is None and sym.live_value is None and sym.ast_info is not None:
        type_str = partial_annotation(sym.ast_info.value_repr)

    if type_str is None:
        if sym.inferred_type_str:
            type_str = sym.inferred_type_str
            ctx.diagnostics.info(
                Stage.EMIT,
                sym.name,
                f"Inferred type {type_str!r} for {sym.name!r} from"
                f" {'literal default' if sym.live_value is None else 'runtime value'}.",
            )
        else:
            ctx.diagnostics.info(
                Stage.EMIT,
                sym.name,
                f"No annotation and no inferrable type for {sym.name!r}; omitting from stub.",
            )
            return ""

    return f"{sym.name}: {type_str}"
