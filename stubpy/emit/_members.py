"""
Which members of a live class a stub lists: methods, nested classes, minus synthesized ones.
"""
from __future__ import annotations

import inspect

from stubpy.analysis.harvest.models import ClassInfo
from stubpy.analysis.hints import is_ignored
from stubpy.emit._constants import DATACLASS_GENERATED_METHODS
from stubpy.state.context import StubContext

from ._method_lookup import methods_defined_on
from .special.detect import is_enum
from .special.enum import public_enum_methods


def _is_synthesized(cls: type, name: str) -> bool:
    """Return ``True`` when method *name* was generated at runtime rather than written in source."""
    fn = cls.__dict__.get(name)
    code = getattr(getattr(fn, "__func__", fn), "__code__", None)
    return code is None or code.co_filename.startswith("<")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def stub_method_names(cls: type, info: ClassInfo | None, is_dc: bool, ctx: StubContext) -> list[str]:
    """Return the methods to stub, dropping private ones, generated dataclass methods and enum internals."""
    names = [
        n for n in methods_defined_on(cls)
        if (ctx.config.include_private or not _is_private(n)) and not _typing_synthesized(cls, n)
    ]
    source_names = {m.name for m in info.methods} if info is not None else None
    if info is not None:
        assigned = {a.name for a in info.attributes} - source_names
        names = [n for n in names if n not in assigned]
    if is_dc:
        names = [
            n for n in names
            if n not in DATACLASS_GENERATED_METHODS
            or (source_names is not None and n in source_names)
            or (source_names is None and not _is_synthesized(cls, n))
        ]
    if is_enum(cls):
        names = [
            n for n in public_enum_methods(names)
            if (n in source_names if source_names is not None else _defined_by(cls, n))
        ]
    if "__init__" not in names and "__init__" not in vars(cls) and isinstance(
            vars(cls).get("__signature__"), inspect.Signature):
        names.insert(0, "__init__")
    return names


def _typing_synthesized(cls: type, name: str) -> bool:
    """Return ``True`` for methods ``typing`` adds to a class, such as a ``Protocol``'s placeholder ``__init__``."""
    fn = cls.__dict__.get(name)
    fn = getattr(fn, "__func__", fn)
    return getattr(fn, "__module__", None) in ("typing", "typing_extensions") and cls.__module__ not in (
        "typing", "typing_extensions",
    )


def _defined_by(cls: type, name: str) -> bool:
    """Return ``True`` when ``cls.__dict__[name]`` was written in *cls*'s own module."""
    fn = cls.__dict__.get(name)
    fn = getattr(fn, "__func__", fn)
    return name not in ("__new__", "__init__") and getattr(fn, "__module__", None) == cls.__module__


def _nested_classes(cls: type) -> list[type]:
    """Return the classes defined in *cls*'s body."""
    prefix = f"{cls.__qualname__}."
    return [
        v for v in cls.__dict__.values()
        if issubclass(type(v), type) and getattr(v, "__qualname__", "") == prefix + v.__name__
    ]


def public_nested(cls: type, info: ClassInfo | None, ctx: StubContext) -> list[type]:
    ignored = {c.name for c in info.classes if c.hint_ignore} if info is not None else set()
    return [
        c for c in _nested_classes(cls)
        if (ctx.config.include_private or not _is_private(c.__name__))
        and c.__name__ not in ignored and not is_ignored(c)
    ]
