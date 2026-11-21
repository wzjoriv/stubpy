"""
Register the type aliases of imported sub-modules so stubs keep their names.
"""
from __future__ import annotations

import types as _builtin_types
from typing import Any

from stubpy.state.context import AliasEntry, StubContext


def _is_type_alias(obj: Any) -> bool:
    """Return ``True`` for PEP 604 unions and subscripted generics, not plain classes."""
    try:
        if obj is None or isinstance(obj, (_builtin_types.ModuleType, type)):
            return False
        return isinstance(obj, _builtin_types.UnionType) or bool(getattr(obj, "__args__", None))
    except Exception:
        return False


def build_alias_registry(
    module: _builtin_types.ModuleType,
    import_map: dict[str, str],
    ctx: StubContext,
) -> None:
    """Register the aliases of every public sub-module attribute of *module* in *ctx*.

    Each alias becomes ``<module_alias>.<Name>`` in ``ctx.alias_registry``; the
    sub-module's import statement is recorded in ``ctx.type_module_imports`` when
    it appears in *import_map*.

    Parameters
    ----------
    module : types.ModuleType or None
        The loaded module whose imported sub-modules are scanned; nothing happens
        when it is ``None`` (not imported).
    import_map : dict of str to str
        Local name to import statement for the module's imports.
    ctx : StubContext
        The run state that receives the registry entries.

    Examples
    --------
    >>> import types
    >>> from stubpy.state.context import StubContext
    >>> sub = types.ModuleType("sub")
    >>> sub.Number = int | float
    >>> mod = types.ModuleType("mod")
    >>> mod.sub = sub
    >>> ctx = StubContext()
    >>> build_alias_registry(mod, {"sub": "from pkg import sub"}, ctx)
    >>> [entry.alias_str for entry in ctx.alias_registry], ctx.type_module_imports
    (['sub.Number'], {'sub': 'from pkg import sub'})
    """
    if module is None:
        return
    for local_name, obj in vars(module).items():
        if local_name.startswith("_"):
            continue
        if not isinstance(obj, _builtin_types.ModuleType):
            continue

        module_alias = local_name
        found_any = False

        for type_name, type_obj in vars(obj).items():
            if type_name.startswith("_"):
                continue
            if _is_type_alias(type_obj):
                ctx.alias_registry.append(
                    AliasEntry(type_obj, f"{module_alias}.{type_name}")
                )
                found_any = True

        if found_any and local_name in import_map:
            ctx.type_module_imports[module_alias] = import_map[local_name]
