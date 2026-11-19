"""
Build a :class:`SymbolTable` by merging runtime objects with AST metadata.
"""
from __future__ import annotations

import ast
import builtins
import inspect
import types as _builtin_types
from typing import Any

from stubpy._constants import HIDDEN_MODULE_DUNDERS, MODULE_DUNDER_TYPES, UNINFORMATIVE_VALUE_TYPES
from stubpy.analysis.harvest.models import ASTSymbols, ClassInfo, FunctionInfo, VariableInfo, on_taken_path
from stubpy.analysis.hints import is_ignored
from stubpy.core.diagnostics import DiagnosticCollector, Stage

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
    Classes, aliases and variables that are private or outside ``__all__``
    are held back as hidden symbols; the emitter promotes the ones a stub
    refers to (a TypeVar, a private base class).  A name
    defined more than once (``if``/``else`` or ``try``/``except`` variants)
    keeps its first definition.  Module dunders such as ``__version__`` and
    ``__getattr__`` count as public.

    Parameters
    ----------
    module : types.ModuleType or None
        The loaded module, or ``None`` when the module was not imported (all ``live_*``
        fields are then ``None``).
    module_name : str
        Synthetic module name, used to tell local classes from imported ones.
    ast_symbols : ASTSymbols
        Output of :func:`~stubpy.analysis.harvest.ast_harvest`.
    all_exports : set of str, optional
        When given, public names outside this set are dropped. Defaults to None.
    include_private : bool, optional
        Keep names starting with ``_``. Defaults to False.
    diagnostics : DiagnosticCollector, optional
        Receives notes about variables whose type cannot be determined. Defaults to None.

    Returns
    -------
    SymbolTable
        The populated table.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> table = build_symbol_table(None, "mymod", ast_harvest("class A: ...\\ndef f(): ...\\nX = 1"))
    >>> table.all_names()
    ['A', 'f', 'X']
    """
    table = SymbolTable()
    ast_class_map: dict[str, ClassInfo] = {c.name: c for c in ast_symbols.classes if on_taken_path(c.branch)}
    class_names = {c.name for c in ast_symbols.classes}

    overload_groups_ast: dict[tuple[str, tuple], list[FunctionInfo]] = {}
    for fn in ast_symbols.functions:
        if fn.is_overload:
            overload_groups_ast.setdefault((fn.name, fn.branch), []).append(fn)

    def _live_module(branch: tuple) -> _builtin_types.ModuleType | None:
        return module if on_taken_path(branch) else None

    def _include(name: str) -> bool:
        if name.startswith("__") and name.endswith("__"):
            return True
        if name.startswith("_"):
            return include_private
        if all_exports is not None and name not in all_exports:
            return False
        return True

    def _place(sym: Any, branch: tuple = ()) -> None:
        sym.branch, sym.dormant = branch, not on_taken_path(branch)
        if sym.name.startswith("__") and sym.name.endswith("__") and sym.name in HIDDEN_MODULE_DUNDERS:
            return
        if _include(sym.name):
            table.add(sym)
        else:
            table.add_hidden(sym)

    defined: set[tuple[str, tuple]] = set()

    def _first(name: str, branch: tuple = ()) -> bool:
        if (name, branch) in defined:
            return False
        defined.add((name, branch))
        return True

    for tv in ast_symbols.typevar_decls:
        if not _first(tv.name, tv.branch):
            continue
        live_obj = _live(_live_module(tv.branch), tv.name)
        _place(AliasSymbol(name=tv.name, lineno=tv.lineno, ast_info=tv, live_obj=live_obj), tv.branch)

    for sym in _class_symbols(module, module_name, ast_symbols, ast_class_map, lambda name: True):
        if _first(sym.name, sym.branch):
            _place(sym, sym.branch)

    overloaded = set(overload_groups_ast)
    for fi in ast_symbols.functions:
        if (not _include(fi.name) or fi.is_overload or (fi.name, fi.branch) in overloaded
                or not _first(fi.name, fi.branch)):
            continue
        live_func = _live_callable(_live_module(fi.branch), fi.name)
        if is_ignored(live_func, fi):
            continue
        _place(FunctionSymbol(name=fi.name, lineno=fi.lineno, live_func=live_func, ast_info=fi), fi.branch)

    for (name, branch), variants in overload_groups_ast.items():
        if not _include(name) or not _first(name, branch):
            continue
        live_func = _live_callable(_live_module(branch), name)
        if is_ignored(live_func) or any(v.hint_ignore for v in variants):
            continue
        lineno = variants[0].lineno if variants else 0
        group = OverloadGroup(name=name, lineno=lineno, live_func=live_func)
        for variant_fi in variants:
            group.variants.append(FunctionSymbol(
                name=name,
                lineno=variant_fi.lineno,
                live_func=live_func,
                ast_info=variant_fi,
            ))
        _place(group, branch)

    imported = {imp.local for imp in ast_symbols.imports}
    variables_by_name: dict[tuple[str, tuple], list[VariableInfo]] = {}
    for vi in ast_symbols.variables:
        variables_by_name.setdefault((vi.name, vi.branch), []).append(vi)
    for (name, branch), infos in variables_by_name.items():
        if (name, branch) in defined:
            continue
        sym = _variable_symbol(_live_module(branch), _merge_variable_infos(infos),
                               diagnostics if _include(name) else None, module_name, imported, class_names)
        if name in imported and not sym.annotation_str and not sym.inferred_type_str:
            continue
        defined.add((name, branch))
        _place(sym, branch)

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
                branch=first.branch,
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
            if is_ignored(obj, ai):
                continue
            if ai:
                lineno = ai.lineno
            else:
                try:
                    lineno = inspect.getsourcelines(obj)[1]
                except Exception:
                    lineno = 0
            sym = ClassSymbol(name=obj.__name__, lineno=lineno, live_type=obj, ast_info=ai)
            sym.branch = ai.branch if ai is not None else ()
            entries.append((lineno, sym))
    for ci in ast_symbols.classes:
        if (module is not None and on_taken_path(ci.branch)) or not include(ci.name) or ci.hint_ignore:
            continue
        sym = ClassSymbol(name=ci.name, lineno=ci.lineno, live_type=None, ast_info=ci)
        sym.branch = ci.branch
        entries.append((ci.lineno, sym))

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


def _instance_of_local_class(value_repr: str | None, local_classes: set[str]) -> str | None:
    """Return ``Cls`` for a right-hand side ``Cls(...)`` calling a class defined in the module."""
    try:
        node = ast.parse(value_repr or "", mode="eval").body
    except SyntaxError:
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in local_classes:
        return node.func.id
    return None


def _variable_symbol(
    module: _builtin_types.ModuleType | None,
    vi: VariableInfo,
    diagnostics: DiagnosticCollector | None,
    module_name: str = "",
    imported: set[str] | None = None,
    local_classes: set[str] | None = None,
) -> VariableSymbol:
    """Build a :class:`VariableSymbol`, inferring a type when there is no annotation."""
    live_value = _live(module, vi.name)
    inferred: str | None = None
    if vi.annotation_str is None:
        if live_value is not None:
            inferred = _live_type_name(live_value, module_name, imported or set())
        if inferred is None and vi.inferred_type_str and vi.inferred_type_str != "None":
            inferred = vi.inferred_type_str
        if inferred is None and live_value is None:
            inferred = _instance_of_local_class(vi.value_repr, local_classes or set())
        if inferred is None and vi.name in MODULE_DUNDER_TYPES:
            inferred = MODULE_DUNDER_TYPES[vi.name]
    if inferred is None and vi.annotation_str is None and diagnostics is not None:
        if live_value is not None:
            t = type(live_value).__name__
            if t in UNINFORMATIVE_VALUE_TYPES:
                diagnostics.warning(
                    Stage.SYMBOL_TABLE,
                    vi.name,
                    f"Variable has uninformative runtime type {t!r}; "
                    "stub will omit the type annotation.",
                )
        elif vi.value_repr is not None:
            diagnostics.info(
                Stage.SYMBOL_TABLE,
                vi.name,
                f"Variable RHS {vi.value_repr!r} is not a literal; "
                "type cannot be inferred without importing the module.",
            )
    return VariableSymbol(
        name=vi.name,
        lineno=vi.lineno,
        live_value=live_value,
        annotation_str=vi.annotation_str,
        inferred_type_str=inferred,
        ast_info=vi,
    )
