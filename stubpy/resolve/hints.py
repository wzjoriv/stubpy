"""Runtime introspection of type hints, annotations and method parameters."""
from __future__ import annotations

import builtins
import inspect
import typing
from typing import Any


def unwrap_descriptor(raw: Any) -> Any:
    """Return the function behind a ``classmethod`` / ``staticmethod`` / ``property``."""
    if isinstance(raw, (classmethod, staticmethod)):
        return raw.__func__
    if isinstance(raw, property):
        return raw.fget
    return raw


def get_own_annotations(obj: Any) -> dict[str, Any]:
    """Return the annotations defined directly on *obj*, keeping unresolved names as forward refs."""
    try:
        import annotationlib
    except ImportError:
        try:
            return dict(inspect.get_annotations(obj))
        except Exception:
            return {}
    try:
        return dict(annotationlib.get_annotations(obj, format=annotationlib.Format.FORWARDREF))
    except Exception:
        return {}


def get_hints_for_method(fn: Any) -> dict[str, Any]:
    """Return resolved type hints for *fn*, unwrapping descriptors first; ``{}`` on failure.

    Falls back to evaluating with builtins in scope, then to the raw
    ``__annotations__``.
    """
    if fn is None:
        return {}
    raw = unwrap_descriptor(fn)
    try:
        return typing.get_type_hints(raw)
    except Exception:
        pass
    try:
        localns = vars(builtins).copy()
        localns.update(getattr(raw, "__globals__", {}) or {})
        return typing.get_type_hints(raw, localns=localns)
    except Exception:
        pass
    return getattr(raw, "__annotations__", {})


def get_raw_params(
    cls: type, method_name: str
) -> tuple[list[inspect.Parameter] | None, dict[str, Any]]:
    """Return ``(params, hints)`` for a method defined directly on *cls*, ``self`` / ``cls`` excluded.

    ``params`` is ``None`` when *method_name* is not in ``cls.__dict__`` or
    has no inspectable signature.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return None, {}

    try:
        sig = inspect.signature(unwrap_descriptor(raw))
    except (ValueError, TypeError):
        return None, {}

    params = [p for name, p in sig.parameters.items() if name not in ("self", "cls")]
    return params, get_hints_for_method(raw)
