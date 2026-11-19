"""
Cython source as signatures for a built module, or as a stand-in module object when it is not built.
"""
from __future__ import annotations

import builtins
import dataclasses
import enum
import types
from pathlib import Path
from typing import Any

from ..detect import module_stem
from ..signatures import Signature, normalize_type, parse_signature
from . import read_pyx_file
from .models import PyxClass, PyxFunction, PyxModule


class _Callable:
    """A Cython-style builtin: its ``__doc__`` opens with the ``embedsignature`` line."""

    def __init__(self, fn: PyxFunction, module: str, qualname: str) -> None:
        self.__name__ = fn.name
        self.__qualname__ = qualname
        self.__module__ = module
        self.__doc__ = fn.embedsignature() + (f"\n\n{fn.doc}" if fn.doc else "")

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        return None


def _sibling(module: types.ModuleType) -> PyxModule | None:
    origin = getattr(module, "__file__", None)
    if not origin:
        return None
    source = Path(origin).with_name(module_stem(Path(origin)) + ".pyx")
    try:
        return read_pyx_file(source) if source.is_file() else None
    except (OSError, ValueError):
        return None


def pyx_attribute_types(module: types.ModuleType) -> dict[str, str]:
    """``{Class.attribute: type}`` for the ``cdef public`` / ``readonly`` fields of the ``.pyx`` beside *module*."""
    pyx = _sibling(module)
    found: dict[str, str] = {}
    for c in pyx.classes if pyx is not None else ():
        for name, (ctype, _) in c.attributes.items():
            mapped = normalize_type(ctype, c_style=True)
            if mapped and mapped != "object":
                found[f"{c.name}.{name}"] = mapped
    return found


def pyx_signatures(module: types.ModuleType) -> dict[str, tuple[Signature, str | None]]:
    """``{qualified name: (signature, docstring)}`` from the ``.pyx`` beside *module*'s file; empty without one."""
    pyx = _sibling(module)
    found: dict[str, tuple[Signature, str | None]] = {}
    for qualified, fn in (pyx.signatures().items() if pyx is not None else ()):
        parsed = parse_signature(fn.embedsignature())
        if parsed is not None:
            found[qualified] = (parsed[1], fn.doc)
    return found


def merge_signature(live: Signature, source: Signature) -> Signature:
    """*live* with the types and defaults it lacks taken from the parameter of the same name in *source*."""
    by_name = {p.name: p for p in source.params}
    params = []
    for p in live.params:
        twin = by_name.get(p.name)
        if twin is not None:
            default = p.default if p.default not in (None, "...") or twin.default is None else twin.default
            p = dataclasses.replace(p, annotation=p.annotation or twin.annotation, default=default)
        params.append(p)
    return Signature(tuple(params), live.returns or source.returns)


def synthetic_module(source: Path, name: str) -> types.ModuleType:
    """A module object that looks like the built extension of *source*, for the compiled-module emitters."""
    pyx = read_pyx_file(source)
    module = types.ModuleType(name, pyx.doc)
    module.__file__ = str(source)
    for e in pyx.enums:
        values, nxt = {}, 0
        for member, value in e.members:
            nxt = value if value is not None else nxt
            values[member] = nxt
            nxt += 1
        cls = enum.IntEnum(e.name, values)
        cls.__module__ = name
        setattr(module, e.name, cls)
        for member in values:
            setattr(module, member, cls[member])
    for c in pyx.classes:
        setattr(module, c.name, _class(c, name))
    for fn in pyx.functions:
        setattr(module, fn.name, _Callable(fn, name, fn.name))
    return module


def _class(c: PyxClass, module: str) -> type:
    namespace: dict[str, Any] = {"__doc__": c.doc, "__module__": module}
    for name, (ctype, readonly) in c.attributes.items():
        doc = f"{name}: {normalize_type(ctype, c_style=True) or 'Any'}"
        namespace[name] = property(_Callable(_getter(name), module, name), None if readonly else _setter, doc=doc)
    for fn in c.methods:
        target = _Callable(fn, module, f"{c.name}.{fn.name}")
        if "property" in fn.decorators:
            namespace[fn.name] = property(target, doc=fn.doc)
        elif "staticmethod" in fn.decorators:
            namespace[fn.name] = staticmethod(target)
        elif "classmethod" in fn.decorators:
            namespace[fn.name] = classmethod(target)
        else:
            namespace[fn.name] = target
    bases = tuple(b for b in (getattr(builtins, n, None) for n in c.bases) if isinstance(b, type)) or (object,)
    return type(c.name, bases, namespace)


def _getter(name: str) -> PyxFunction:
    return PyxFunction(name)


def _setter(self: Any, value: Any) -> None:
    return None

