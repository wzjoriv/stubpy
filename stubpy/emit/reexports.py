"""Re-exported imports: the ``from .x import Name as Name`` lines of a module's public surface."""
from __future__ import annotations

from stubpy.analysis.harvest.models import ASTSymbols, ImportInfo
from stubpy.core.context import StubContext


def _defined_names(ast_symbols: ASTSymbols, ctx: StubContext) -> set[str]:
    """Return the names the stub defines itself: the symbol table, else every harvested definition."""
    if ctx.symbol_table is not None:
        return set(ctx.symbol_table.all_names())
    return (
        {c.name for c in ast_symbols.classes}
        | {f.name for f in ast_symbols.functions}
        | {v.name for v in ast_symbols.variables}
        | {t.name for t in ast_symbols.typevar_decls}
    )


def _is_exported(imp: ImportInfo, ctx: StubContext, is_package: bool) -> bool:
    """Return ``True`` when the imported name is part of the module's public surface."""
    local = imp.local
    if ctx.all_exports is not None and ctx.config.respect_all:
        return local in ctx.all_exports
    if local.startswith("_") and not ctx.config.include_private:
        return False
    return is_package and imp.module is not None and imp.module.startswith(".")


def _render(imp: ImportInfo) -> str:
    if imp.module is None:
        if imp.asname:
            return f"import {imp.name} as {imp.asname}"
        return f"import {imp.name}" if "." in imp.name else f"import {imp.name} as {imp.name}"
    return f"from {imp.module} import {imp.name} as {imp.local}"


def reexport_lines(ast_symbols: ASTSymbols, ctx: StubContext, is_package: bool = False) -> list[str]:
    """Return the import lines that re-export names from the module's stub.

    A name is re-exported when ``__all__`` lists it, or, without
    ``__all__``, when a package ``__init__`` imports it relatively.  A star
    import from a module that declares ``__all__`` becomes one re-export
    per name (``ctx.star_exports``); other star imports are kept.  Names the module also defines are skipped,
    so ``try: from fast import f / except ImportError: def f(): ...`` keeps
    one definition.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> syms = ast_harvest("from .core import Canvas")
    >>> reexport_lines(syms, StubContext(), is_package=True)
    ['from .core import Canvas as Canvas']
    """
    defined = _defined_names(ast_symbols, ctx)
    lines: list[str] = []
    seen: set[str] = set()
    for imp in ast_symbols.imports:
        if imp.module == "__future__":
            continue
        if imp.name == "*":
            names = ctx.star_exports.get(imp.module or "")
            if names is None:
                line = f"from {imp.module} import *"
            else:
                for name in names:
                    if name in defined or name in seen or name.startswith("__"):
                        continue
                    seen.add(name)
                    if ctx.all_exports is None or not ctx.config.respect_all or name in ctx.all_exports:
                        lines.append(f"from {imp.module} import {name} as {name}")
                continue
        elif imp.local in defined or imp.local in seen or not _is_exported(imp, ctx, is_package):
            continue
        else:
            line = _render(imp)
            seen.add(imp.local)
        if line not in lines:
            lines.append(line)
    return lines
