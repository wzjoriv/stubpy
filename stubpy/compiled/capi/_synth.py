"""
A module object built from an extension's C sources alone, for stubbing it without importing it.
"""
from __future__ import annotations

import builtins
import types
from pathlib import Path
from typing import Any

from .models import CModule

_PLACEHOLDERS: dict[str, Any] = {"int": 0, "str": "", "float": 0.0, "bool": False, "bytes": b"", "dict": {},
                                 "list": [], "tuple": ()}


class _Builtin:
    """A C function: its ``__doc__`` opens with the ``name(params) -> ret`` line read from the source."""

    def __init__(self, name: str, module: str, qualname: str, doc: str) -> None:
        self.__name__ = name
        self.__qualname__ = qualname
        self.__module__ = module
        self.__doc__ = doc

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        return None


def c_source_module(path: Path, name: str, found: CModule) -> types.ModuleType:
    """A module named *name* for the extension at *path* with the functions, classes, constants and exceptions in *found*.

    Examples
    --------
    >>> from pathlib import Path
    >>> from stubpy.compiled.capi import read_c_source
    >>> found = read_c_source('''
    ... static PyObject *add(PyObject *self, PyObject *args) {
    ...     int a; if (!PyArg_ParseTuple(args, "i", &a)) return NULL; return PyLong_FromLong(a);
    ... }
    ... static PyMethodDef methods[] = {{"add", add, METH_VARARGS, NULL}, {NULL}};
    ... PyMODINIT_FUNC PyInit__m(void) { PyObject *m = PyModule_Create(&def);
    ...     PyModule_AddIntConstant(m, "LEVEL", 3); return m; }
    ... ''')
    >>> module = c_source_module(Path("_m.pyd"), "_m", found)
    >>> module.add.__doc__, module.LEVEL
    ('add(a: int, /) -> int', 0)
    """
    module = types.ModuleType(name)
    module.__file__ = str(path)
    classes: dict[str, dict[str, Any]] = {cls: {"__module__": name} for cls in found.classes.values()}
    for qualname, sig in found.signatures.items():
        owner, _, attr = qualname.rpartition(".")
        doc = found.docs.get(qualname) or ""
        if not doc.startswith(f"{attr}("):
            doc = f"{attr}{sig.render()}" + (f"\n\n{doc}" if doc else "")
        if owner:
            classes.setdefault(owner, {"__module__": name})[attr] = _Builtin(attr, name, qualname, doc)
        else:
            setattr(module, attr, _Builtin(attr, name, attr, doc))
    for cls, namespace in classes.items():
        setattr(module, cls, type(cls, (), namespace))
    for exc, base in found.exceptions.items():
        parent = getattr(builtins, base, Exception)
        setattr(module, exc, type(exc, (parent if isinstance(parent, type) else Exception,), {"__module__": name}))
    for const, kind in found.constants.items():
        if not hasattr(module, const):
            setattr(module, const, _PLACEHOLDERS.get(kind, object()))
    return module
