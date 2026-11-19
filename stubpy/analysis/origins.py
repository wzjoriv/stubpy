"""
Where a module-level name comes from: follow ``from x import y`` chains to the defining module.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types as _builtin_types
import typing
from functools import lru_cache
from typing import Any

from stubpy._constants import TARGET_MODULE_PREFIX

from . import vfs
from .imports import scan_import_statements

_TYPEVAR_LIKE: tuple[type, ...] = tuple(
    t for t in (getattr(typing, n, None) for n in ("TypeVar", "ParamSpec", "TypeVarTuple")) if isinstance(t, type)
)
_TYPE_ALIAS_TYPE = getattr(typing, "TypeAliasType", None)
_NEW_TYPE = getattr(typing, "NewType", None)


def is_named_type(obj: Any) -> bool:
    """Return ``True`` for objects a stub must keep by name: type aliases, ``NewType`` and PEP 695 aliases.

    Classes, modules and TypeVars are not included; they render by name anyway.

    Parameters
    ----------
    obj : Any
        The runtime object of a module-level name.

    Returns
    -------
    bool
        Whether *obj* is a named type alias.

    Examples
    --------
    >>> from typing import Union
    >>> is_named_type(Union[int, str]), is_named_type(int | None), is_named_type(int)
    (True, True, False)
    """
    if obj is None or isinstance(obj, (_builtin_types.ModuleType, type)) or isinstance(obj, _TYPEVAR_LIKE):
        return False
    if _TYPE_ALIAS_TYPE is not None and isinstance(obj, _TYPE_ALIAS_TYPE):
        return True
    if isinstance(_NEW_TYPE, type) and isinstance(obj, _NEW_TYPE):
        return True
    if isinstance(obj, _builtin_types.UnionType):
        return True
    try:
        return bool(getattr(obj, "__args__", None)) or getattr(obj, "__origin__", None) is not None
    except Exception:
        return False


@lru_cache(maxsize=512)
def _imports_of(path: str, mtime: float) -> dict[str, str]:
    """Return ``{local: statement}`` for the module-level imports in the file at *path*."""
    try:
        return scan_import_statements(ast.parse(vfs.read_source(path)))
    except (OSError, SyntaxError, ValueError):
        return {}


def _module_imports(module: _builtin_types.ModuleType) -> dict[str, str]:
    path = getattr(module, "__file__", None)
    if not isinstance(path, str) or not path.endswith(".py"):
        return {}
    try:
        mtime = vfs.mtime(path)
    except OSError:
        return {}
    return _imports_of(path, mtime)


def origin_of(module_name: str, name: str, _depth: int = 0) -> tuple[str, str] | None:
    """Return ``(defining_module, name_there)`` for the global *name* of the loaded module *module_name*.

    ``from x import y`` statements are followed through package re-exports; a
    name the module does not import is taken as defined there.

    Parameters
    ----------
    module_name : str
        Name of a module present in ``sys.modules``.
    name : str
        A global of that module.

    Returns
    -------
    tuple of (str, str) or None
        The defining module and the name used there; ``None`` when the module is
        not loaded, the name is not one of its globals, or the chain cannot be
        followed (star imports, synthetic target modules).

    Examples
    --------
    >>> origin_of("json", "JSONDecodeError")
    ('json.decoder', 'JSONDecodeError')
    """
    module = sys.modules.get(module_name)
    if module is None or _depth > 16 or module_name.startswith(TARGET_MODULE_PREFIX):
        return None
    if name not in vars(module):
        return None
    stmt = _module_imports(module).get(name)
    if stmt is None:
        return module_name, name
    try:
        node = ast.parse(stmt).body[0]
    except (SyntaxError, IndexError):
        return None
    if not isinstance(node, ast.ImportFrom):
        return None
    alias = node.names[0]
    relative = "." * node.level + (node.module or "")
    try:
        target = importlib.util.resolve_name(relative, module.__package__ or "") if node.level else relative
    except (ImportError, ValueError):
        return None
    return origin_of(target, alias.name, _depth + 1) or (target, alias.name)


def relative_module(target: str, current: str, current_is_package: bool) -> str:
    """Return *target* relative to the module *current* when both share a top-level package, else *target*.

    Parameters
    ----------
    target : str
        Absolute dotted name of the module to import.
    current : str
        Dotted name of the importing module.
    current_is_package : bool
        Whether *current* is a package (an ``__init__`` module).

    Returns
    -------
    str
        The relative form with leading dots, or *target* unchanged.

    Examples
    --------
    >>> relative_module("pkg.a.b", "pkg.c.d", False)
    '..a.b'
    >>> relative_module("pkg.a", "pkg", True)
    '.a'
    >>> relative_module("other.x", "pkg.c", False)
    'other.x'
    """
    package = current if current_is_package else current.rpartition(".")[0]
    if not package or target.split(".")[0] != current.split(".")[0]:
        return target
    pkg_parts, tgt_parts = package.split("."), target.split(".")
    common = 0
    while common < min(len(pkg_parts), len(tgt_parts)) and pkg_parts[common] == tgt_parts[common]:
        common += 1
    dots = "." * (len(pkg_parts) - common + 1)
    return dots + ".".join(tgt_parts[common:])
