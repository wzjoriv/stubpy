"""Module-level variable stubs."""
from __future__ import annotations

from stubpy.analysis.symbols.models import VariableSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticStage


def generate_variable_stub(sym: VariableSymbol, ctx: StubContext) -> str:
    """Generate a ``name: Type`` line for a module-level variable.

    Uses the source annotation, else the inferred type (noted as an INFO
    diagnostic); returns ``""`` when neither exists.

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
    type_str = sym.annotation_str

    if type_str is None:
        if sym.inferred_type_str:
            type_str = sym.inferred_type_str
            ctx.diagnostics.info(
                DiagnosticStage.EMIT,
                sym.name,
                f"Inferred type {type_str!r} for {sym.name!r} from"
                f" {'literal default' if sym.live_value is None else 'runtime value'}.",
            )
        else:
            ctx.diagnostics.info(
                DiagnosticStage.EMIT,
                sym.name,
                f"No annotation and no inferrable type for {sym.name!r}; omitting from stub.",
            )
            return ""

    return f"{sym.name}: {type_str}"
