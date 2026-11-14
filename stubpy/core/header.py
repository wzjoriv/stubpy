"""Import header assembly for a generated stub."""
from __future__ import annotations

import types

from stubpy._constants import FUTURE_IMPORT
from stubpy.analysis.imports import (
    collect_cross_imports,
    collect_decorator_imports,
    collect_special_imports,
    collect_typing_imports,
)

from .context import StubContext


def build_header(
    body: str,
    ctx: StubContext,
    module: types.ModuleType | None,
    module_name: str,
    import_map: dict[str, str],
    reexports: list[str] | None = None,
) -> list[str]:
    """Return the deduplicated import lines a stub *body* needs, ``__future__`` import first.

    Order: names from ``typing``, ``abc``, ``dataclasses``, ``enum``,
    ``functools`` and ``typing_extensions`` (one line per module), used
    alias modules, cross-file imports from the source, imports the emitters
    asked for, then the module's re-exports.
    """
    header_lines = [FUTURE_IMPORT]
    seen: set[str] = set()

    def _add(stmt: str) -> None:
        if stmt not in seen:
            seen.add(stmt)
            header_lines.append(stmt)

    from_names: dict[str, set[str]] = {"typing": set(collect_typing_imports(body))}
    for source in (collect_special_imports(body), collect_decorator_imports(body)):
        for mod, names in source.items():
            from_names.setdefault(mod, set()).update(names)
    from_names["typing"] -= from_names.get("typing_extensions", set())
    for mod in ["typing"] + sorted(m for m in from_names if m != "typing"):
        if from_names[mod]:
            _add(f"from {mod} import {', '.join(sorted(from_names[mod]))}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            _add(import_stmt)

    reexports = reexports or []
    covered = {stmt.rpartition(" as ")[0] for stmt in reexports}
    for stmt in sorted(collect_cross_imports(module, module_name, body, import_map)):
        if stmt not in covered:
            _add(stmt)
    for stmt in sorted(set(ctx.extra_imports.values())):
        if stmt not in covered:
            _add(stmt)
    for stmt in reexports:
        _add(stmt)

    return header_lines
