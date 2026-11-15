"""Import header assembly for a generated stub."""
from __future__ import annotations

import types

from stubpy.analysis.imports import (
    collect_cross_imports,
    collect_decorator_imports,
    collect_special_imports,
    collect_typing_imports,
)

from ._imports import ImportSet
from .context import StubContext


def build_header(
    body: str,
    ctx: StubContext,
    module: types.ModuleType | None,
    module_name: str,
    import_map: dict[str, str],
    reexports: list[str] | None = None,
) -> list[str]:
    """Return the import lines a stub *body* needs, ``__future__`` import first.

    Every bound name is imported once.  When two imports bind the same
    name, the first in this order wins: the module's re-exports, imports
    taken from the source, imports the emitters added, then the names
    stubpy supplies itself (``typing``, ``abc``, ``enum``, ``dataclasses``,
    ``functools``, ``contextlib``, ``typing_extensions``).  Names from one
    module share one sorted line; absolute modules come before relative ones.
    """
    imports = ImportSet()
    for stmt in reexports or []:
        imports.add(stmt)

    source_stmts = set(import_map.values())
    for stmt in collect_cross_imports(module, module_name, body, import_map):
        imports.add(stmt)
    for alias, stmt in sorted(ctx.used_type_imports.items()):
        if stmt and f"{alias}." in body:
            imports.add(stmt)
    extra = sorted(set(ctx.extra_imports.values()), key=lambda s: s not in source_stmts)
    for stmt in extra:
        imports.add(stmt)

    bound = imports.bound()
    supplied: dict[str, set[str]] = {}
    for source in (collect_special_imports(body), collect_decorator_imports(body)):
        for mod, names in source.items():
            supplied.setdefault(mod, set()).update(names)
    typing_names = set(collect_typing_imports(body)) - set().union(*supplied.values()) if supplied else set(
        collect_typing_imports(body)
    )
    supplied.setdefault("typing", set()).update(typing_names)
    for mod in ["typing"] + sorted(m for m in supplied if m != "typing"):
        imports.add_names(mod, sorted(supplied[mod] - bound))

    return imports.lines()
