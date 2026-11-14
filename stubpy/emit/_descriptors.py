"""Descriptor introspection for method emission."""
from __future__ import annotations

import inspect

from stubpy.resolve import unwrap_callable, unwrap_descriptor


def is_async_callable(raw: object) -> bool:
    """Return ``True`` if *raw* wraps a coroutine or async generator function."""
    fn = unwrap_descriptor(raw)
    if fn is None:
        return False
    return any(
        inspect.iscoroutinefunction(f) or inspect.isasyncgenfunction(f)
        for f in (fn, unwrap_callable(fn))
    )


def is_abstract_method(raw: object) -> bool:
    """Return ``True`` if *raw* wraps a function with ``__isabstractmethod__`` set."""
    fn = unwrap_descriptor(raw)
    if fn is None:
        return False
    return bool(getattr(fn, "__isabstractmethod__", False))


def find_property_mro(cls: type, prop_name: str) -> property | None:
    """Return a property merging the first getter, setter and deleter found along *cls*'s MRO."""
    fget = fset = fdel = None
    for klass in cls.__mro__:
        obj = klass.__dict__.get(prop_name)
        if not isinstance(obj, property):
            continue
        if fget is None and obj.fget is not None:
            fget = obj.fget
        if fset is None and obj.fset is not None:
            fset = obj.fset
        if fdel is None and obj.fdel is not None:
            fdel = obj.fdel
        if fget is not None and fset is not None and fdel is not None:
            break

    if fget is None and fset is None and fdel is None:
        return None
    return property(fget, fset, fdel)
