"""Types of module and class constants, and whether a C-level descriptor accepts assignment."""
from __future__ import annotations

import types
from typing import Any

from ..typemap import TypeMapper

_SCALARS = (bool, int, float, complex, str, bytes)
_PROBE = object()
_instances: dict[int, tuple[type, Any]] = {}


def _item_type(items: list[Any]) -> str | None:
    kinds = {type(v) for v in items}
    if len(kinds) == 1 and next(iter(kinds)) in _SCALARS:
        return next(iter(kinds)).__name__
    return None


def value_type(value: Any, mapper: TypeMapper, local: dict[type, str]) -> str:
    """The annotation for a constant: scalars and homogeneous containers by type, instances by class."""
    if value is None:
        return "None"
    if type(value) in _SCALARS:
        return type(value).__name__
    if isinstance(value, tuple):
        item = _item_type(list(value))
        return f"tuple[{item}, ...]" if item else "tuple[Any, ...]"
    if isinstance(value, (list, set, frozenset)):
        item = _item_type(list(value))
        return f"{type(value).__name__}[{item or 'Any'}]"
    if isinstance(value, dict):
        key, val = _item_type(list(value)), _item_type(list(value.values()))
        return f"dict[{key or 'Any'}, {val or 'Any'}]"
    cls = type(value)
    if cls in local:
        return local[cls]
    return mapper(f"{cls.__module__}.{cls.__qualname__}") or "Any" if "<" not in cls.__qualname__ else "Any"


def _instance(cls: type) -> Any:
    """A throwaway instance made with ``cls.__new__(cls)`` (no ``__init__``), or ``None``."""
    cached = _instances.get(id(cls))
    if cached is not None and cached[0] is cls:
        return cached[1]
    try:
        inst = cls.__new__(cls)
    except Exception:
        inst = None
    _instances[id(cls)] = (cls, inst)
    return inst


def is_writable(cls: type, descriptor: Any) -> bool:
    """Whether assigning through *descriptor* can succeed.

    A ``property`` is writable when it has ``fset``.  A getset or member
    descriptor is probed on a ``cls.__new__(cls)`` instance with a dummy
    value: :exc:`AttributeError` means read-only, anything else (usually a
    ``TypeError`` from the setter) means writable.  Without an instance the
    descriptor counts as writable, as in mypy's stubgen.
    """
    if isinstance(descriptor, property):
        return descriptor.fset is not None
    if not isinstance(descriptor, (types.GetSetDescriptorType, types.MemberDescriptorType)):
        return hasattr(descriptor, "__set__")
    inst = _instance(cls)
    if inst is None:
        return True
    try:
        descriptor.__set__(inst, _PROBE)
    except AttributeError:
        return False
    except Exception:
        return True
    return True


def clear_instances() -> None:
    """Forget the probe instances."""
    _instances.clear()
