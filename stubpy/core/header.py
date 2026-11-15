"""Import header assembly for a generated stub."""
from __future__ import annotations

import types

from stubpy._constants import FUTURE_IMPORT
from stubpy.analysis.imports import (
    collect_cross_imports,
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
) -> list[str]:
    """Return the deduplicated import lines a stub *body* needs, ``__future__`` import first.

    Order: ``typing`` names, ``abc`` / ``dataclasses`` / ``enum``, used
    alias modules, then cross-file imports from the source.
    """
    header_lines = [FUTURE_IMPORT]
    seen: set[str] = set()

    def _add(stmt: str) -> None:
        if stmt not in seen:
            seen.add(stmt)
            header_lines.append(stmt)

    typing_names = collect_typing_imports(body)
    if typing_names:
        _add(f"from typing import {', '.join(typing_names)}")

    for module_name_s, names in sorted(collect_special_imports(body).items()):
        _add(f"from {module_name_s} import {', '.join(names)}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            _add(import_stmt)

    if module is not None:
        for stmt in sorted(collect_cross_imports(module, module_name, body, import_map)):
            _add(stmt)

    return header_lines
