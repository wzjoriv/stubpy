"""
Types of module and class constants, and whether a C-level descriptor accepts assignment.
"""
from __future__ import annotations

import sys
import types
from typing import Any

from ..typemap import TypeMapper

_SCALARS = (bool, int, float, complex, str, bytes)
_PROBE = object()
_instances: dict[int, tuple[type, Any]] = {}
_pinned: list[Any] = []


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
    if cls.__name__ == "PyCapsule":
        return mapper("typing_extensions.CapsuleType") or "Any"
    if callable(value) and not isinstance(value, type) and cls.__module__ == "builtins":
        return "Callable[..., Any]"
    return mapper(f"{cls.__module__}.{cls.__qualname__}") or "Any" if "<" not in cls.__qualname__ else "Any"


def _instance(cls: type) -> Any:
    """A probe instance made with ``cls.__new__(cls)`` (no ``__init__``), or ``None``.

    It is never freed: a compiled class may crash when an instance whose ``__init__`` never
    ran is deallocated.
    """
    cached = _instances.get(id(cls))
    if cached is not None and cached[0] is cls:
        return cached[1]
    try:
        inst = cls.__new__(cls)
    except Exception:
        inst = None
    if inst is not None:
        _keep_alive(inst)
    _instances[id(cls)] = (cls, inst)
    return inst


def _keep_alive(obj: Any) -> None:
    """Hold an extra reference to *obj* that is never released (CPython), so it is never deallocated."""
    _pinned.append(obj)
    if sys.implementation.name == "cpython":
        try:
            import ctypes
            ctypes.pythonapi.Py_IncRef(ctypes.py_object(obj))
        except (ImportError, AttributeError, OSError):
            pass


def _c_writable(descriptor: Any) -> bool | None:
    """Writability read from a CPython getset / member descriptor's C definition; ``None`` elsewhere.

    The definition pointer is the descriptor object's last field, so its offset is the descriptor
    type's ``__basicsize__`` minus a pointer, also on free-threaded builds.

    Examples
    --------
    >>> import sys, types
    >>> ro = types.FunctionType.__dict__["__globals__"]          # member, READONLY
    >>> rw = types.FunctionType.__dict__["__doc__"]              # getset with a setter
    >>> sys.implementation.name != "cpython" or (_c_writable(ro), _c_writable(rw)) == (False, True)
    True
    """
    if sys.implementation.name != "cpython":
        return None
    try:
        import ctypes
        pointer = ctypes.sizeof(ctypes.c_void_p)
        definition = ctypes.c_void_p.from_address(id(descriptor) + type(descriptor).__basicsize__ - pointer).value
        if not definition:
            return None
        if isinstance(descriptor, types.GetSetDescriptorType):
            return bool(ctypes.c_void_p.from_address(definition + 2 * pointer).value)  # name, get, set
        flags = ctypes.c_int.from_address(definition + pointer + 2 * ctypes.sizeof(ctypes.c_ssize_t)).value
        return not flags & 1  # name, type (padded), offset, flags; READONLY = 1
    except (ImportError, OSError, ValueError, AttributeError):
        return None


def is_writable(cls: type, descriptor: Any) -> bool:
    """Whether assigning through *descriptor* can succeed.

    A ``property`` is writable when it has ``fset``.  On CPython a getset or
    member descriptor is read from its C definition (a NULL setter, the
    ``READONLY`` flag) without calling anything: calling a setter on an
    instance whose ``__init__`` never ran can crash the process.  Elsewhere it
    is probed on a ``cls.__new__(cls)`` instance with a dummy value:
    :exc:`AttributeError` means read-only, anything else means writable.
    Without an instance the descriptor counts as writable, as in mypy's stubgen.
    """
    if isinstance(descriptor, property):
        return descriptor.fset is not None
    if not isinstance(descriptor, (types.GetSetDescriptorType, types.MemberDescriptorType)):
        return hasattr(descriptor, "__set__")
    known = _c_writable(descriptor)
    if known is not None:
        return known
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
