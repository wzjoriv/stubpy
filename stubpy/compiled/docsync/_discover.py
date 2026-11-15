"""Find and import the module a hand-written stub describes, and read its runtime docstrings."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

from stubpy._constants import COMPILED_SOURCE_SUFFIXES, SOURCE_SUFFIX
from stubpy.analysis.loader import find_import_target

from ..detect import SLOT_WRAPPER_TYPES, is_current_abi, is_extension_file, module_stem
from ..signatures import strip_signature_lines

_SLOT_TYPES = SLOT_WRAPPER_TYPES


def sibling_module_file(stub: Path) -> Path | None:
    """The module file next to *stub* with the same stem: an importable extension, else a ``.pyx`` / C source, else ``.py``."""
    stem = stub.name[: -len(stub.suffix)] if stub.suffix else stub.name
    found = [p for p in stub.parent.iterdir() if p != stub and p.is_file() and module_stem(p) == stem]
    for wanted in (lambda p: is_extension_file(p) and is_current_abi(p),
                   lambda p: p.suffix in COMPILED_SOURCE_SUFFIXES,
                   lambda p: p.suffix == SOURCE_SUFFIX):
        match = sorted(p for p in found if wanted(p))
        if match:
            return match[0]
    return None


def module_name_for(stub: Path) -> tuple[str, Path | None]:
    """The dotted name of the module *stub* describes and the folder to import it from."""
    sibling = sibling_module_file(stub)
    if sibling is None:
        raise ModuleNotFoundError(f"No module file next to {stub} (expected {stub.stem}.pyx or {stub.stem}.*.pyd / .so)")
    target = find_import_target(sibling)
    if target is not None:
        return target.name, target.root
    return module_stem(sibling), sibling.parent


def import_module(name: str, root: Path | None = None) -> types.ModuleType:
    """Import *name*, with *root* first on ``sys.path`` while importing."""
    saved = list(sys.path)
    if root is not None:
        sys.path.insert(0, str(root))
    try:
        return importlib.import_module(name)
    finally:
        sys.path[:] = saved


def stub_for_module(module: types.ModuleType) -> Path:
    """The ``.pyi`` next to a module's file (``pkg/_x.cp311-win_amd64.pyd`` gives ``pkg/_x.pyi``)."""
    origin = getattr(module, "__file__", None)
    if not origin:
        raise FileNotFoundError(f"{module.__name__} has no file, so it has no stub next to it")
    path = Path(origin)
    return path.with_name(module_stem(path) + ".pyi")


def _resolve(module: types.ModuleType, path: list[str]) -> tuple[Any, Any]:
    """``(owner, object)`` for a qualified path inside *module*; ``(None, None)`` when it does not exist."""
    owner: Any = module
    obj: Any = module
    for part in path:
        owner = obj
        namespace = vars(obj) if isinstance(obj, type) else None
        obj = namespace.get(part) if namespace is not None and part in namespace else getattr(obj, part, None)
        if obj is None:
            return None, None
    return owner, obj


def runtime_docstring(module: types.ModuleType, path: list[str]) -> str | None:
    """The runtime docstring for a stub definition, without binding signature lines; ``None`` to leave it alone."""
    owner, obj = _resolve(module, path)
    if obj is None or isinstance(obj, _SLOT_TYPES):
        return None
    if isinstance(obj, (staticmethod, classmethod)):
        obj = obj.__func__
    doc = getattr(obj, "__doc__", None)
    if not isinstance(doc, str) or not doc.strip():
        return None
    name = path[-1]
    inherited = getattr(object, name, None) if isinstance(owner, type) else None
    if inherited is not None and getattr(inherited, "__doc__", None) == doc:
        return None
    if isinstance(obj, type):
        if "__members__" in vars(obj):
            doc = doc.partition("\n\nMembers:")[0]
        if isinstance(owner, types.ModuleType) and obj.__module__ != module.__name__:
            return None
        return strip_signature_lines(obj.__name__, doc) or None
    return strip_signature_lines(name, doc) or None
