"""
stubpy.aliases
==============

Alias registry builder.

Scans a loaded module for imported type sub-modules and registers their
type aliases into a :class:`~stubpy.context.StubContext`. Once registered,
:func:`~stubpy.annotations.annotation_to_str` emits ``types.Length``
instead of expanding it to ``str | float | int``.
"""
from __future__ import annotations

import types as _builtin_types
from typing import Any

from .context import AliasEntry, StubContext


def _is_type_alias(obj: Any) -> bool:
    """Return ``True`` if *obj* is a runtime type alias suitable for registration.

    Accepts PEP 604 unions (``str | int``) and subscripted typing generics
    (``List[str]``, ``Literal["a"]``). Rejects plain classes, modules,
    ``None``, and bare unsubscripted aliases such as ``List``.

    Parameters
    ----------
    obj : Any
        Any Python object to test.

    Returns
    -------
    bool
        ``True`` when *obj* should be stored as an alias entry.
    """
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
    """Scan *module* for type sub-modules and populate *ctx* with their aliases.

    For each attribute of *module* that is itself a module object this
    function iterates its public attributes and registers every type alias
    it finds as an :class:`~stubpy.context.AliasEntry` in
    ``ctx.alias_registry``. The corresponding import statement is recorded
    in ``ctx.type_module_imports`` so it can be re-emitted in the ``.pyi``
    header.

    Only sub-modules that appear in *import_map* are scanned, meaning
    they must have been explicitly imported in the source file via
    ``from pkg import types``. This prevents accidentally scanning
    standard-library modules that happen to be present in the namespace.

    Parameters
    ----------
    module : types.ModuleType
        The loaded source module returned by
        :func:`~stubpy.loader.load_module`.
    import_map : dict
        Mapping of ``local_name -> import_statement`` produced by
        :func:`~stubpy.imports.scan_import_statements`.
    ctx : StubContext
        The :class:`~stubpy.context.StubContext` to populate in-place.
        ``ctx.alias_registry`` and ``ctx.type_module_imports`` are
        extended; other fields are left unchanged.

    Notes
    -----
    Private attributes (names starting with ``_``) are skipped both at
    the parent-module level and inside each type sub-module.

    Examples
    --------
    >>> import types as _t
    >>> from stubpy.context import StubContext
    >>> from stubpy.aliases import build_alias_registry
    >>> types_mod = _t.ModuleType("mytypes")
    >>> types_mod.Length = str | float | int
    >>> parent = _t.ModuleType("mypkg")
    >>> parent.types = types_mod
    >>> ctx = StubContext()
    >>> build_alias_registry(parent, {"types": "from mypkg import types"}, ctx)
    >>> ctx.alias_registry[0].alias_str
    'types.Length'
    >>> ctx.type_module_imports["types"]
    'from mypkg import types'
    """
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
