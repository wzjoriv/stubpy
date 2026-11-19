"""
Lazy module attributes (PEP 562): emit the names ``__getattr__`` provides, and drop it once all are known.
"""
from __future__ import annotations

import ast
import builtins
import types
from typing import Any

from stubpy._constants import UNINFORMATIVE_VALUE_TYPES
from stubpy.analysis.harvest import ASTSymbols, ImportInfo
from stubpy.analysis.lazy import module_import, static_lazy_exports
from stubpy.analysis.symbols import VariableSymbol

from .context import StubContext
from .diagnostics import Stage


def _static_names(ast_symbols: ASTSymbols) -> set[str]:
    """Return every name the source binds at module level."""
    return (
        {c.name for c in ast_symbols.classes} | {f.name for f in ast_symbols.functions}
        | {v.name for v in ast_symbols.variables} | {t.name for t in ast_symbols.typevar_decls}
        | {i.local for i in ast_symbols.imports}
    )


def _module_path(name: str, package: str | None) -> str:
    """Return *name* relative to *package* when it lies beneath it, else unchanged."""
    if package and name.startswith(package + "."):
        return "." + name[len(package) + 1:]
    return name


def _runtime_import(obj: Any, name: str, module: types.ModuleType) -> ImportInfo | None:
    """Return the import that binds the live *obj* as *name*, for modules, classes and functions of other modules."""
    package = getattr(module, "__package__", None)
    if isinstance(obj, types.ModuleType):
        return module_import(_module_path(obj.__name__, package), name)
    origin = getattr(obj, "__module__", None)
    qualname = getattr(obj, "__qualname__", None)
    if (isinstance(origin, str) and isinstance(qualname, str) and qualname.isidentifier()
            and origin != module.__name__ and (isinstance(obj, type) or callable(obj))):
        return ImportInfo(_module_path(origin, package), qualname, name)
    return None


def _value_type(obj: Any) -> str | None:
    """Return a builtin type name for a plain lazy value, else ``None``."""
    kind = type(obj)
    if getattr(builtins, kind.__name__, None) is kind and kind.__name__ not in UNINFORMATIVE_VALUE_TYPES:
        return kind.__name__
    return None


def _render(imp: ImportInfo) -> str:
    if imp.module is None:
        return f"import {imp.name} as {imp.local}"
    return f"from {imp.module} import {imp.name} as {imp.local}"


def lazy_reexports(tree: ast.Module | None, module: types.ModuleType | None, ast_symbols: ASTSymbols,
                   ctx: StubContext) -> list[str]:
    """Return the re-export lines of the names a module ``__getattr__`` provides lazily.

    Lazy names are the ``__all__`` entries neither the source, a star
    import nor the live namespace binds, and the keys of the mappings or
    ``if name == ...`` branches in ``__getattr__``; the ones the source
    already imports (under ``TYPE_CHECKING``, say) are emitted as usual.  Each resolves from the source, else (runtime) from
    ``getattr(module, name)``: other modules' objects become re-exports,
    plain values typed variables.  ``__getattr__`` leaves the stub when it
    ends by raising and every lazy name was resolved.
    """
    lazy = static_lazy_exports(tree) if tree is not None else None
    table = ctx.symbol_table
    if lazy is None or table is None:
        return []
    static = _static_names(ast_symbols)
    bound = static | {n for names in ctx.star_exports.values() for n in names} | set(ctx.module_namespace)
    lazy_names = {
        n for n in set(lazy.names) | ((ctx.all_exports or set()) - bound)
        if not n.startswith("_") or ctx.config.include_private
    }
    candidates = lazy_names - static
    resolved: dict[str, ImportInfo | None] = dict(lazy.imports)
    for name in sorted(candidates - set(resolved)):
        obj = _live_attribute(module, name)
        imp = _runtime_import(obj, name, module) if obj is not None else None
        value_type = (_value_type(obj) if obj is not None else None) or lazy.values.get(name)
        if imp is not None:
            resolved[name] = imp
        elif value_type:
            table.add(VariableSymbol(name, lazy.lineno, live_value=obj, inferred_type_str=value_type))
            resolved[name] = None
    missing = sorted(candidates - set(resolved))
    if lazy_names and not missing and lazy.closed:
        table.discard("__getattr__")
    elif missing:
        ctx.diagnostics.info(
            Stage.SYMBOL_TABLE, "__getattr__",
            f"Module __getattr__ is kept: lazy name(s) {', '.join(missing)} could not be resolved",
        )
    return [_render(imp) for name, imp in sorted(resolved.items()) if imp is not None and name in candidates]


def _live_attribute(module: types.ModuleType | None, name: str) -> Any | None:
    """Return ``getattr(module, name)``, running its ``__getattr__``; ``None`` on any failure."""
    if module is None:
        return None
    try:
        return getattr(module, name)
    except Exception:
        return None
