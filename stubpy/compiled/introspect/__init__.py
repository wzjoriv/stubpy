"""
Build the :class:`~stubpy.extend.SymbolTable` of a live compiled module.
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Any

from stubpy.analysis.exports import runtime_all
from stubpy.analysis.symbols import ClassSymbol, FunctionSymbol, OverloadGroup, SymbolTable, VariableSymbol
from stubpy.state.diagnostics import DiagnosticCollector, Stage

from ..capi import capi_attribute_types, capi_signatures
from ..detect import is_compiled_callable
from ..pyx import pyx_attribute_types, pyx_signatures
from ..typemap import TypeMapper
from ._classes import class_info
from ._functions import Scope, callable_infos, is_hint_ignored
from ._hand_stub import sibling_annotations
from ._values import clear_instances, value_type

__all__ = ["CompiledTable", "build_compiled_table"]


@dataclass
class CompiledTable:
    """The symbol table of a compiled module and the imports its annotations need.

    Attributes
    ----------
    table : SymbolTable
        The module's symbols; hidden ones are kept out of the stub.
    imports : dict of str to str
        Import statements the annotations need, keyed by the bound name.
    all_names : list of str or None
        The module's ``__all__``, or ``None`` when it defines none.
    """
    table: SymbolTable
    imports: dict[str, str] = field(default_factory=dict)
    all_names: list[str] | None = None


def _defined_here(obj: Any, module_name: str) -> bool:
    """True unless *obj* says it comes from another module."""
    owner = getattr(obj, "__module__", None)
    return not isinstance(owner, str) or owner == module_name


def _add(table: SymbolTable, symbol: Any, visible: bool) -> None:
    if visible:
        table.add(symbol)
    else:
        table.add_hidden(symbol)


def _function_symbol(name: str, obj: Any, scope: Scope, lineno: int) -> Any:
    infos = callable_infos(name, obj, scope)
    if len(infos) == 1:
        infos[0].lineno = lineno
        return FunctionSymbol(name, lineno, ast_info=infos[0])
    variants = []
    for info in infos:
        info.lineno = lineno
        variants.append(FunctionSymbol(name, lineno, ast_info=info))
    return OverloadGroup(name, lineno, variants=variants)


def build_compiled_table(
    module: types.ModuleType,
    *,
    diagnostics: DiagnosticCollector | None = None,
    include_private: bool = False,
    include_docstrings: bool = False,
    respect_all: bool = True,
) -> CompiledTable:
    """Introspect a compiled *module* into a symbol table.

    Parameters
    ----------
    module : module
        The imported extension module.
    diagnostics : DiagnosticCollector, optional
        Receives an INFO for every callable stubbed without a signature.
    include_private : bool, optional
        As the :class:`~stubpy.Config` field of the same name.
        Defaults to ``False``.
    include_docstrings : bool, optional
        As the :class:`~stubpy.Config` field of the same name.
        Defaults to ``False``.
    respect_all : bool, optional
        As the :class:`~stubpy.Config` field of the same name.
        Defaults to ``True``.

    Returns
    -------
    CompiledTable
        The table (private names and names outside ``__all__`` are hidden),
        the imports the annotations need and the module's ``__all__``.

    Examples
    --------
    >>> import types
    >>> mod = types.ModuleType("mypkg_ext")
    >>> mod.LIMIT = 3
    >>> build_compiled_table(mod).table.all_names()
    ['LIMIT']
    """
    name = module.__name__
    namespace = vars(module)
    local_classes = {
        obj: key for key, obj in namespace.items()
        if isinstance(obj, type) and _defined_here(obj, name) and obj.__name__ == key
    }
    mapper = TypeMapper(name, set(namespace))
    scope = Scope(name, mapper, diagnostics if diagnostics is not None else DiagnosticCollector(),
                  include_docstrings=include_docstrings, include_private=include_private,
                  hand={**capi_attribute_types(module), **pyx_attribute_types(module), **sibling_annotations(module)},
                  pyx={**capi_signatures(module), **pyx_signatures(module)})
    exported = runtime_all(module)
    table = SymbolTable()
    try:
        for lineno, (key, obj) in enumerate(namespace.items(), start=1):
            if key.startswith("__") or isinstance(obj, types.ModuleType) or is_hint_ignored(obj):
                continue
            visible = (include_private or not key.startswith("_")) and (
                exported is None or not respect_all or key in exported)
            if isinstance(obj, type):
                if obj in local_classes:
                    _add(table, ClassSymbol(key, lineno, ast_info=class_info(obj, scope, lineno)), visible)
            elif is_compiled_callable(obj) or callable(obj) and _defined_here(obj, name):
                if _defined_here(obj, name):
                    _add(table, _function_symbol(key, obj, scope, lineno), visible)
            else:
                ann = value_type(obj, mapper, local_classes)
                _add(table, VariableSymbol(key, lineno, annotation_str=ann), visible)
    finally:
        clear_instances()
    scope.diagnostics.info(Stage.SYMBOL_TABLE, name, f"Compiled module introspected: {len(table)} symbols")
    return CompiledTable(table, dict(mapper.imports), exported)
