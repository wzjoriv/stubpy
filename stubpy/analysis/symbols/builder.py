"""Build a :class:`SymbolTable` by merging runtime objects with AST metadata."""
from __future__ import annotations

import inspect
import types as _builtin_types
from typing import Any

from stubpy._constants import UNINFORMATIVE_VALUE_TYPES
from stubpy.analysis.harvest.models import ASTSymbols, ClassInfo, FunctionInfo, VariableInfo
from stubpy.core.diagnostics import DiagnosticCollector, DiagnosticStage

from .models import AliasSymbol, ClassSymbol, FunctionSymbol, OverloadGroup, VariableSymbol
from .table import SymbolTable


def build_symbol_table(
    module: _builtin_types.ModuleType | None,
    module_name: str,
    ast_symbols: ASTSymbols,
    all_exports: set[str] | None = None,
    include_private: bool = False,
    diagnostics: DiagnosticCollector | None = None,
) -> SymbolTable:
    """Build a :class:`SymbolTable` from AST metadata and, when available, the live module.

    Symbols are added in this order: type aliases / TypeVars, classes
    (sorted by source line), functions, overload groups, variables.

    Parameters
    ----------
    module : types.ModuleType or None
        The loaded module, or ``None`` in AST-only mode (all ``live_*``
        fields are then ``None``).
    module_name : str
        Synthetic module name, used to tell local classes from imported ones.
    ast_symbols : ASTSymbols
        Output of :func:`~stubpy.ast_harvest`.
    all_exports : set of str or None
        When given, public names outside this set are dropped.
    include_private : bool
        Keep names starting with ``_``.  Defaults to ``False``.
    diagnostics : DiagnosticCollector or None
        Receives notes about variables whose type cannot be determined.

    Returns
    -------
    SymbolTable
        The populated table.
    """
    table = SymbolTable()
    ast_class_map: dict[str, ClassInfo] = {c.name: c for c in ast_symbols.classes}

    overload_groups_ast: dict[str, list[FunctionInfo]] = {}
    for fn in ast_symbols.functions:
        if fn.is_overload:
            overload_groups_ast.setdefault(fn.name, []).append(fn)

    def _include(name: str) -> bool:
        if name.startswith("_"):
            return include_private
        if all_exports is not None and name not in all_exports:
            return False
        return True

    for tv in ast_symbols.typevar_decls:
        if not _include(tv.name):
            continue
        live_obj = getattr(module, tv.name, None) if module is not None else None
        table.add(AliasSymbol(name=tv.name, lineno=tv.lineno, ast_info=tv, live_obj=live_obj))

    for sym in _class_symbols(module, module_name, ast_symbols, ast_class_map, _include):
        table.add(sym)

    for fi in ast_symbols.functions:
        if not _include(fi.name) or fi.is_overload:
            continue
        table.add(FunctionSymbol(
            name=fi.name,
            lineno=fi.lineno,
            live_func=_live_callable(module, fi.name),
            ast_info=fi,
        ))

    for name, variants in overload_groups_ast.items():
        if not _include(name):
            continue
        live_func = _live_callable(module, name)
        lineno = variants[0].lineno if variants else 0
        group = OverloadGroup(name=name, lineno=lineno, live_func=live_func)
        for variant_fi in variants:
            group.variants.append(FunctionSymbol(
                name=name,
                lineno=variant_fi.lineno,
                live_func=live_func,
                ast_info=variant_fi,
            ))
        table.add(group)

    for vi in ast_symbols.variables:
        if not _include(vi.name):
            continue
        table.add(_variable_symbol(module, vi, diagnostics))

    return table


def _live_callable(module: _builtin_types.ModuleType | None, name: str) -> Any | None:
    """Return ``module.<name>`` when it is callable, else ``None``."""
    if module is None:
        return None
    candidate = getattr(module, name, None)
    return candidate if callable(candidate) else None


def _class_symbols(
    module: _builtin_types.ModuleType | None,
    module_name: str,
    ast_symbols: ASTSymbols,
    ast_class_map: dict[str, ClassInfo],
    include: Any,
) -> list[ClassSymbol]:
    """Return the class symbols to emit, sorted by source line."""
    entries: list[tuple[int, ClassSymbol]] = []

    if module is not None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if getattr(obj, "__module__", None) != module_name:
                continue
            if not include(obj.__name__):
                continue
            ai = ast_class_map.get(obj.__name__)
            if ai:
                lineno = ai.lineno
            else:
                try:
                    lineno = inspect.getsourcelines(obj)[1]
                except Exception:
                    lineno = 0
            entries.append((lineno, ClassSymbol(
                name=obj.__name__, lineno=lineno, live_type=obj, ast_info=ai,
            )))
    else:
        for ci in ast_symbols.classes:
            if not include(ci.name):
                continue
            entries.append((ci.lineno, ClassSymbol(
                name=ci.name, lineno=ci.lineno, live_type=None, ast_info=ci,
            )))

    return [sym for _, sym in sorted(entries, key=lambda t: t[0])]


def _variable_symbol(
    module: _builtin_types.ModuleType | None,
    vi: VariableInfo,
    diagnostics: DiagnosticCollector | None,
) -> VariableSymbol:
    """Build a :class:`VariableSymbol`, inferring a type when there is no annotation."""
    live_value = getattr(module, vi.name, None) if module is not None else None
    inferred: str | None = None
    if vi.annotation_str is None:
        if live_value is not None:
            inferred = type(live_value).__name__
        elif vi.inferred_type_str:
            inferred = vi.inferred_type_str
    if inferred is None and vi.annotation_str is None and diagnostics is not None:
        if live_value is not None:
            t = type(live_value).__name__
            if t in UNINFORMATIVE_VALUE_TYPES:
                diagnostics.warning(
                    DiagnosticStage.SYMBOL_TABLE,
                    vi.name,
                    f"Variable has uninformative runtime type {t!r}; "
                    "stub will omit the type annotation.",
                )
        elif vi.value_repr is not None:
            diagnostics.info(
                DiagnosticStage.SYMBOL_TABLE,
                vi.name,
                f"Variable RHS {vi.value_repr!r} is not a literal; "
                "type cannot be inferred in AST-only mode.",
            )
    return VariableSymbol(
        name=vi.name,
        lineno=vi.lineno,
        live_value=live_value,
        annotation_str=vi.annotation_str,
        inferred_type_str=inferred,
        ast_info=vi,
    )
