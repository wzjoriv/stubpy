"""Recognise extension-module files, compiled modules, compiled classes and compiled callables."""
from __future__ import annotations

import importlib.machinery
import inspect
import re
import types
from pathlib import Path
from typing import Any

from stubpy._constants import EXTENSION_FILE_SUFFIXES

__all__ = [
    "is_extension_file",
    "module_stem",
    "is_current_abi",
    "is_compiled_module",
    "is_compiled_callable",
    "SLOT_WRAPPER_TYPES",
]

_ABI_TAG = re.compile(r"\.[\w-]+$")

SLOT_WRAPPER_TYPES: tuple[type, ...] = tuple(
    t for t in (types.WrapperDescriptorType, types.MethodWrapperType)
    if t not in (types.FunctionType, types.MethodType)
)


def is_extension_file(path: str | Path) -> bool:
    """True for a ``.pyd`` / ``.so`` file, whatever interpreter it was built for."""
    return Path(path).suffix in EXTENSION_FILE_SUFFIXES


def module_stem(path: str | Path) -> str:
    """The module name a file defines: ``_x.cp311-win_amd64.pyd`` gives ``_x``."""
    p = Path(path)
    if not is_extension_file(p):
        return p.stem
    return _ABI_TAG.sub("", p.stem) if "." in p.stem else p.stem


def is_current_abi(path: str | Path) -> bool:
    """True when this interpreter imports the extension file: its whole suffix (ABI tag included) is one it loads."""
    name = Path(path).name
    return name[len(module_stem(path)):] in importlib.machinery.EXTENSION_SUFFIXES


def is_compiled_module(module: Any) -> bool:
    """True for a module loaded from an extension file."""
    if not isinstance(module, types.ModuleType):
        return False
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) or getattr(module, "__file__", None) or ""
    return is_extension_file(origin)


def is_compiled_callable(obj: Any) -> bool:
    """True for a callable implemented in native code (C API, Cython, pybind11, nanobind)."""
    if obj is None or isinstance(obj, type) or inspect.isfunction(obj) or inspect.ismethod(obj):
        return False
    if isinstance(obj, (staticmethod, classmethod)):
        return is_compiled_callable(obj.__func__)
    return callable(obj) and not hasattr(obj, "py_func")
