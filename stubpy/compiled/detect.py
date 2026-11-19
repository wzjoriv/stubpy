"""
Recognise extension-module files, compiled modules, compiled classes and compiled callables.
"""
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
    """Report whether a path is an extension-module file.

    Matches ``.pyd`` and ``.so`` suffixes whatever interpreter the file was
    built for.

    Parameters
    ----------
    path : str or pathlib.Path
        The file to test.

    Returns
    -------
    bool
        ``True`` for a ``.pyd`` or ``.so`` file.

    Examples
    --------
    >>> is_extension_file("_x.cp311-win_amd64.pyd"), is_extension_file("x.py")
    (True, False)
    """
    return Path(path).suffix in EXTENSION_FILE_SUFFIXES


def module_stem(path: str | Path) -> str:
    """Return the module name a file defines.

    For an extension file the ABI tag is dropped, so
    ``_x.cp311-win_amd64.pyd`` gives ``_x``.

    Parameters
    ----------
    path : str or pathlib.Path
        A source or extension-module file.

    Returns
    -------
    str
        The module name without suffix or ABI tag.

    Examples
    --------
    >>> module_stem("pkg/_x.cp311-win_amd64.pyd")
    '_x'
    >>> module_stem("pkg/mod.py")
    'mod'
    """
    p = Path(path)
    if not is_extension_file(p):
        return p.stem
    return _ABI_TAG.sub("", p.stem) if "." in p.stem else p.stem


def is_current_abi(path: str | Path) -> bool:
    """Report whether this interpreter can import an extension file.

    The file's whole suffix, ABI tag included, must be one this interpreter
    loads.

    Parameters
    ----------
    path : str or pathlib.Path
        The extension file.

    Returns
    -------
    bool
        ``True`` when the file's suffix is in
        :data:`importlib.machinery.EXTENSION_SUFFIXES`.

    Examples
    --------
    >>> is_current_abi("_x.cp1-nothing.pyd")
    False
    """
    name = Path(path).name
    return name[len(module_stem(path)):] in importlib.machinery.EXTENSION_SUFFIXES


def is_compiled_module(module: Any) -> bool:
    """Report whether a module was loaded from an extension file.

    Parameters
    ----------
    module : Any
        The object to test; anything other than a module gives ``False``.

    Returns
    -------
    bool
        ``True`` when the module's origin is a ``.pyd`` or ``.so`` file.

    Examples
    --------
    >>> import json
    >>> is_compiled_module(json), is_compiled_module("json")
    (False, False)
    """
    if not isinstance(module, types.ModuleType):
        return False
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) or getattr(module, "__file__", None) or ""
    return is_extension_file(origin)


def is_compiled_callable(obj: Any) -> bool:
    """Report whether an object is a callable implemented in native code.

    Covers the C API, Cython, pybind11 and nanobind.  Python functions,
    bound methods, classes and Cython-compiled functions that keep a
    ``py_func`` do not count.

    Parameters
    ----------
    obj : Any
        The object to test.

    Returns
    -------
    bool
        ``True`` for a native callable.

    Examples
    --------
    >>> is_compiled_callable(len), is_compiled_callable(lambda: 0)
    (True, False)
    """
    if obj is None or isinstance(obj, type) or inspect.isfunction(obj) or inspect.ismethod(obj):
        return False
    if isinstance(obj, (staticmethod, classmethod)):
        return is_compiled_callable(obj.__func__)
    return callable(obj) and not hasattr(obj, "py_func")
