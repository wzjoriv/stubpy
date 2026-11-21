"""
Import header assembly for a generated stub.
"""
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
from stubpy.state.context import StubContext

from ._imports import ImportSet, parse_entries

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

    Parameters
    ----------
    body : str
        The stub text the imports must serve.
    ctx : StubContext
        Run state: alias imports, emitter imports and the target Python version.
    module : types.ModuleType or None
        The imported module, or ``None`` when it was analysed from source.
    module_name : str
        Dotted name of the module being stubbed.
    import_map : dict of str to str
        ``{local_name: import_statement}`` for the imports in the source.
    reexports : list of str, optional
        Import statements for the module's re-exports.  Defaults to ``None``.
    exclude : set of str, optional
        Names bound inside version branches.  Defaults to an empty set.

    Returns
    -------
    list of str
        The import lines, sorted and grouped per module.

    Examples
    --------
    >>> from stubpy.state.context import StubContext
    >>> build_header("x: Optional[int]\\n", StubContext(), None, "m", {})
    ['from typing import Optional']
    """
    imports = ImportSet()
    for stmt in reexports or []:
        imports.add(stmt)

    source_stmts = set(import_map.values())
    import_map = {k: v for k, v in import_map.items() if k not in exclude}
    for stmt in collect_cross_imports(module, module_name, body, import_map):
        imports.add(stmt)
    for stmt in _module_values(body, ctx, import_map):
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
    imports.retarget(ctx.config.target_version)
    return imports.lines()


def _module_values(body: str, ctx: StubContext, import_map: dict[str, str]) -> list[str]:
    """``import numpy as np`` for names the stub uses as ``np.X`` that hold a module but were not imported.

    Covers modules bound by a call (``np = pytest.importorskip("numpy")``, ``importlib.import_module``).
    """
    found = []
    for name in sorted(set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\.\w", body))):
        value = ctx.module_namespace.get(name) if ctx.module_namespace else None
        if name in import_map or not isinstance(value, types.ModuleType):
            continue
        real = value.__name__
        found.append(f"import {real}" if real == name else f"import {real} as {name}")
    return found
