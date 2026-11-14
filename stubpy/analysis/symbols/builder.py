"""Build a :class:`SymbolTable` by merging runtime objects with AST metadata."""
from __future__ import annotations

import builtins
import inspect
import types as _builtin_types
from typing import Any

from stubpy._constants import HIDDEN_MODULE_DUNDERS, MODULE_DUNDER_TYPES, UNINFORMATIVE_VALUE_TYPES
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
    (sorted by source line), functions, overload groups, variables.  A name
    defined more than once (``if``/``else`` or ``try``/``except`` variants)
    keeps its first definition.  Module dunders such as ``__version__`` and
    ``__getattr__`` count as public.

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
        if name.startswith("__") and name.endswith("__"):
            return name not in HIDDEN_MODULE_DUNDERS
        if name.startswith("_"):
            return include_private
        if all_exports is not None and name not in all_exports:
            return False
        return True

    defined: set[str] = set()

    def _first(name: str) -> bool:
        if name in defined:
            return False
        defined.add(name)
        return True

    for tv in ast_symbols.typevar_decls:
        if not _include(tv.name) or not _first(tv.name):
            continue
        table.add(AliasSymbol(name=tv.name, lineno=tv.lineno, ast_info=tv, live_obj=_live(module, tv.name)))

    for sym in _class_symbols(module, module_name, ast_symbols, ast_class_map, _include):
        if _first(sym.name):
            table.add(sym)

    overloaded = set(overload_groups_ast)
    for fi in ast_symbols.functions:
        if not _include(fi.name) or fi.is_overload or fi.name in overloaded or not _first(fi.name):
            continue
        table.add(FunctionSymbol(
            name=fi.name,
            lineno=fi.lineno,
            live_func=_live_callable(module, fi.name),
            ast_info=fi,
        ))

    for name, variants in overload_groups_ast.items():
        if not _include(name) or not _first(name):
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

    imported = {imp.local for imp in ast_symbols.imports}
    variables_by_name: dict[str, list[VariableInfo]] = {}
    for vi in ast_symbols.variables:
        variables_by_name.setdefault(vi.name, []).append(vi)
    for name, infos in variables_by_name.items():
        if not _include(name) or name in defined:
            continue
        sym = _variable_symbol(module, _merge_variable_infos(infos), diagnostics, module_name, imported)
        if name in imported and not sym.annotation_str and not sym.inferred_type_str:
            continue
        defined.add(name)
        table.add(sym)

    return table


def _merge_variable_infos(infos: list[VariableInfo]) -> VariableInfo:
    """Return the first assignment of a variable, borrowing a type from a later one when it has none."""
    first = infos[0]
    if first.annotation_str or first.inferred_type_str:
        return first
    for later in infos[1:]:
        if later.annotation_str or later.inferred_type_str:
            return VariableInfo(
                name=first.name,
                lineno=first.lineno,
                annotation_str=later.annotation_str,
                value_repr=first.value_repr,
                inferred_type_str=later.inferred_type_str,
            )
    return first


def _live(module: _builtin_types.ModuleType | None, name: str) -> Any | None:
    """Return ``module.<name>`` from its namespace, without triggering a module ``__getattr__``."""
    if module is None:
        return None
    try:
        return vars(module).get(name)
    except TypeError:
        return None


def _live_callable(module: _builtin_types.ModuleType | None, name: str) -> Any | None:
    """Return ``module.<name>`` when it is callable, else ``None``."""
    candidate = _live(module, name)
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
        for obj in list(vars(module).values()):
            if not isinstance(obj, type) or getattr(obj, "__module__", None) != module_name:
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


def _live_type_name(value: Any, module_name: str, imported: set[str]) -> str | None:
    """Return a type name for *value* that is valid in the stub: a builtin, a local class or an imported one."""
    kind = type(value)
    name = kind.__name__
    if getattr(builtins, name, None) is kind:
        return None if name in UNINFORMATIVE_VALUE_TYPES else name
    if kind.__module__ == module_name and "<" not in kind.__qualname__:
        return kind.__qualname__
    return name if name in imported else None


def _variable_symbol(
    module: _builtin_types.ModuleType | None,
    vi: VariableInfo,
    diagnostics: DiagnosticCollector | None,
    module_name: str = "",
    imported: set[str] | None = None,
) -> VariableSymbol:
    """Build a :class:`VariableSymbol`, inferring a type when there is no annotation."""
    live_value = _live(module, vi.name)
    inferred: str | None = None
    if vi.annotation_str is None:
        if live_value is not None:
            inferred = _live_type_name(live_value, module_name, imported or set())
        if inferred is None and vi.inferred_type_str and vi.inferred_type_str != "None":
            inferred = vi.inferred_type_str
        if inferred is None and vi.name in MODULE_DUNDER_TYPES:
            inferred = MODULE_DUNDER_TYPES[vi.name]
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
