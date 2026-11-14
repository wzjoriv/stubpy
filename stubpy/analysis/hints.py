"""Read ``stubpy.hint`` decorators from live objects and from harvested AST metadata."""
from __future__ import annotations

from typing import Any

from stubpy._constants import HINT_IGNORE_ATTR, HINT_RETURNS_ATTR, HINT_SIGNATURE_ATTR

_WRAPPER_ATTRS = ("__func__", "fget", "func", "py_func", "__wrapped__")
_MAX_DEPTH = 8


def live_hint(obj: Any, attr: str) -> Any:
    """Return *attr* from *obj* or the callables it wraps (descriptors, ``functools.wraps``, JIT dispatchers)."""
    seen: set[int] = set()
    stack = [obj]
    while stack and len(seen) < _MAX_DEPTH:
        current = stack.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        try:
            namespace = vars(current)
        except TypeError:
            namespace = {}
        if attr in namespace:
            return namespace[attr]
        if isinstance(current, type):
            continue
        for wrapper in _WRAPPER_ATTRS:
            try:
                inner = namespace.get(wrapper) if wrapper == "__wrapped__" else getattr(current, wrapper, None)
            except Exception:
                inner = None
            if inner is not None:
                stack.append(inner)
    return None


def is_ignored(obj: Any, info: Any = None) -> bool:
    """Return ``True`` when ``@hint.ignore`` is on the live object or in its AST info."""
    if info is not None and getattr(info, "hint_ignore", False):
        return True
    return obj is not None and live_hint(obj, HINT_IGNORE_ATTR) is True


def signature_hint(obj: Any, info: Any = None) -> str | None:
    """Return the ``@hint.signature`` text from the live object, else from its AST info."""
    value = live_hint(obj, HINT_SIGNATURE_ATTR) if obj is not None else None
    if isinstance(value, str):
        return value
    return getattr(info, "hint_signature", None) if info is not None else None


def returns_hint(obj: Any, info: Any = None) -> str | None:
    """Return the ``@hint.returns`` text from the live object, else from its AST info."""
    value = live_hint(obj, HINT_RETURNS_ATTR) if obj is not None else None
    if isinstance(value, str):
        return value
    return getattr(info, "hint_returns", None) if info is not None else None
