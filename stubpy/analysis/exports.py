"""A module's export list: ``__all__`` with spliced entries, and the names a star import binds."""
from __future__ import annotations

import importlib.util
import sys
import types as _builtin_types
from functools import lru_cache
from pathlib import Path

from . import vfs
from .harvest import ASTSymbols, ast_harvest


@lru_cache(maxsize=256)
def _harvest_file(path: str, mtime: float) -> ASTSymbols | None:
    try:
        return ast_harvest(vfs.read_source(path))
    except (OSError, SyntaxError, ValueError):
        return None


def harvest_file(path: Path) -> ASTSymbols | None:
    """Return the AST harvest of the file at *path*, cached per modification time; ``None`` when unreadable."""
    try:
        return _harvest_file(str(path), vfs.mtime(path))
    except OSError:
        return None


def module_file(current: Path, module: str) -> Path | None:
    """Return the source file of *module* (relative dots allowed) as imported from the file *current*.

    Absolute names resolve against the root of *current*'s package tree.
    """
    dots = len(module) - len(module.lstrip("."))
    parts = [p for p in module.lstrip(".").split(".") if p]
    if dots:
        base = current.parent
        for _ in range(dots - 1):
            base = base.parent
    else:
        base = current.parent
        while vfs.is_file(base / "__init__.py"):
            base = base.parent
    target = base.joinpath(*parts) if parts else base
    if vfs.is_file(target / "__init__.py"):
        return target / "__init__.py"
    file = target.with_suffix(".py")
    return file if parts and vfs.is_file(file) else None


def static_all(path: Path, symbols: ASTSymbols | None = None, _depth: int = 0) -> list[str] | None:
    """Return ``__all__`` of the file at *path* from its source, following ``*other.__all__`` splices.

    A spliced name must come from ``from m import __all__ as name``;
    ``None`` when ``__all__`` is missing or cannot be read statically.
    """
    symbols = symbols if symbols is not None else harvest_file(path)
    if symbols is None or symbols.all_exports is None or _depth > 16:
        return None
    names = list(symbols.all_exports)
    for spliced in symbols.all_spliced:
        imp = next((i for i in symbols.imports if i.local == spliced and i.name == "__all__"), None)
        target = module_file(path, imp.module) if imp is not None and imp.module else None
        extra = static_all(target, None, _depth + 1) if target is not None else None
        if extra is None:
            return None
        names.extend(extra)
    return names


def runtime_all(module: _builtin_types.ModuleType | None) -> list[str] | None:
    """Return the live module's ``__all__`` when it is a list or tuple of strings, else ``None``."""
    try:
        names = getattr(module, "__all__", None) if module is not None else None
    except Exception:
        return None
    if isinstance(names, (list, tuple)) and all(isinstance(n, str) for n in names):
        return list(names)
    return None


def star_names(
    module_ref: str, path: Path, package: str | None, live: bool,
) -> list[str] | None:
    """Return the names ``from <module_ref> import *`` binds when the target declares ``__all__``.

    With *live*, the imported module's runtime ``__all__`` is used (the
    module is looked up in ``sys.modules`` relative to *package*);
    otherwise its source is read.  ``None`` when the target has no
    ``__all__``: a stub then keeps the star import.
    """
    if live:
        try:
            name = importlib.util.resolve_name(module_ref, package or "") if module_ref.startswith(".") else module_ref
        except (ImportError, ValueError):
            name = None
        names = runtime_all(sys.modules.get(name)) if name else None
        if names is not None:
            return names
    target = module_file(path, module_ref)
    return static_all(target) if target is not None else None
