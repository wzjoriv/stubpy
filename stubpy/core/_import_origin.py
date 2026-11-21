"""
``from M import X`` where *M* only imports *X* itself: a stub does not re-export a plain import, so import *X*
from where *M* got it.
"""
from __future__ import annotations

from stubpy.state.context import StubContext

from ._imports import parse_entries

_MAX_HOPS = 8


def through_reexports(stmt: str, ctx: StubContext) -> str:
    """Return *stmt*, a one-name ``from`` import, pointed past modules that merely import the name.

    A module that defines the name, lists it in ``__all__`` or imports it as ``X as X`` exports it;
    anything else is followed to its origin. Statements outside the run's source index are kept.

    Examples
    --------
    >>> through_reexports("import os", StubContext())
    'import os'
    """
    entries = parse_entries(stmt)
    index, here = ctx.source_index, ctx.source_module
    if len(entries) != 1 or index is None or here is None:
        return stmt
    entry = entries[0]
    if entry.module is None or entry.name == "*":
        return stmt
    bound = entry.asname or entry.name
    module_text, name, current = entry.module, entry.name, here
    changed = False
    for _ in range(_MAX_HOPS):
        owner = index.import_from(current, module_text)
        if owner is None:
            break
        symbols = owner.symbols
        if _defines(symbols, name) or name in (symbols.all_exports or []):
            break
        imp = next((i for i in reversed(symbols.imports) if i.local == name and i.name != "*"), None)
        if imp is None or imp.asname == imp.name or imp.branch:
            break
        if imp.module is None:
            return _plain(imp.name, imp.asname, bound)
        module_text, name, current, changed = _absolute(imp.module, owner.package), imp.name, owner, True
    if not changed:
        return stmt
    return f"from {module_text} import {name}" + (f" as {bound}" if bound != name else "")


def _defines(symbols, name: str) -> bool:
    return any(c.name == name for c in symbols.classes) or any(f.name == name for f in symbols.functions) or any(
        v.name == name for v in symbols.variables) or any(t.name == name for t in symbols.typevar_decls)


def _plain(dotted: str, asname: str | None, bound: str) -> str:
    """``import a.b as bound``; a plain ``import a.b`` binds ``a``, which is *bound* only when it is ``a``."""
    if asname is None and dotted.split(".")[0] == bound:
        return f"import {dotted}"
    return f"import {dotted} as {bound}" if dotted != bound else f"import {dotted}"


def _absolute(module: str, package: str) -> str:
    """*module* with leading dots resolved against *package*."""
    level = len(module) - len(module.lstrip("."))
    if level == 0:
        return module
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)] if level > 1 else parts
    rest = module[level:]
    return ".".join([*base, rest] if rest else base)
