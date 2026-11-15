"""Import header assembly for a generated stub."""
from __future__ import annotations

import re
import types

from stubpy.analysis.imports import (
    collect_cross_imports,
    collect_decorator_imports,
    collect_modern_imports,
    collect_special_imports,
    collect_typing_imports,
)

from ._imports import ImportSet, parse_entries
from .context import StubContext

_WORD_RE = re.compile(r"\b[A-Za-z_]\w*\b")


def build_header(
    body: str,
    ctx: StubContext,
    module: types.ModuleType | None,
    module_name: str,
    import_map: dict[str, str],
    reexports: list[str] | None = None,
    exclude: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """Return the import lines a stub *body* needs.

    Every bound name is imported once.  When two imports bind the same
    name, the first in this order wins: the module's re-exports, imports
    taken from the source, imports the emitters added, then the names
    stubpy supplies itself (``typing``, ``abc``, ``enum``, ``dataclasses``,
    ``functools``, ``contextlib``, ``typing_extensions``).  Names from one
    module share one sorted line; absolute modules come before relative ones.
    Names in *exclude* (bound inside version branches) are never imported here.
    """
    imports = ImportSet()
    for stmt in reexports or []:
        imports.add(stmt)

    source_stmts = set(import_map.values())
    import_map = {k: v for k, v in import_map.items() if k not in exclude}
    for stmt in collect_cross_imports(module, module_name, body, import_map):
        imports.add(stmt)
    for alias, stmt in sorted(ctx.used_type_imports.items()):
        if stmt and f"{alias}." in body:
            imports.add(stmt)
    extra = sorted(set(ctx.extra_imports.values()), key=lambda s: s not in source_stmts)
    words = set(_WORD_RE.findall(body))
    for stmt in extra:
        if any(e.bound.split(".")[0] in words for e in parse_entries(stmt)):
            imports.add(stmt)

    bound = imports.bound() | set(exclude)
    supplied: dict[str, set[str]] = {}
    for source in (collect_special_imports(body), collect_decorator_imports(body), collect_modern_imports(body)):
        for mod, names in source.items():
            supplied.setdefault(mod, set()).update(names)
    typing_names = set(collect_typing_imports(body)) - set().union(*supplied.values()) if supplied else set(
        collect_typing_imports(body)
    )
    supplied.setdefault("typing", set()).update(typing_names)
    for mod in ["typing"] + sorted(m for m in supplied if m != "typing"):
        imports.add_names(mod, sorted(supplied[mod] - bound))

    return imports.lines()
