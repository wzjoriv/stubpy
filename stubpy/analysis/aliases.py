"""Register the type aliases of imported sub-modules so stubs keep their names."""
from __future__ import annotations

import types as _builtin_types
from typing import Any

from stubpy.core.context import AliasEntry, StubContext


def _is_type_alias(obj: Any) -> bool:
    """Return ``True`` for PEP 604 unions and subscripted generics, not plain classes."""
    if obj is None:
        return False
    if isinstance(obj, (_builtin_types.ModuleType, type)):
        return False
    if isinstance(obj, _builtin_types.UnionType):
        return True
    if getattr(obj, "__args__", None):
        return True
    return False


def build_alias_registry(
    module: _builtin_types.ModuleType,
    import_map: dict[str, str],
    ctx: StubContext,
) -> None:
    """Register the aliases of every public sub-module attribute of *module* in *ctx*.

    Each alias becomes ``<module_alias>.<Name>`` in ``ctx.alias_registry``;
    the sub-module's import statement is recorded in
    ``ctx.type_module_imports`` when it appears in *import_map*.  Does
    nothing when *module* is ``None`` (not imported).
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
