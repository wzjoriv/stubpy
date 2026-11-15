"""Runtime introspection of type hints, annotations and method parameters."""
from __future__ import annotations

import inspect
from typing import Any

from stubpy._constants import POS_KW, POS_ONLY

from .callables import hints_of, signature_of

try:
    import annotationlib
except ImportError:
    annotationlib = None


def unwrap_descriptor(raw: Any) -> Any:
    """Return the function behind a ``classmethod`` / ``staticmethod`` / ``property``."""
    if isinstance(raw, (classmethod, staticmethod)):
        return raw.__func__
    if isinstance(raw, property):
        return raw.fget
    return raw


def get_own_annotations(obj: Any) -> dict[str, Any]:
    """Return the annotations defined directly on *obj*, keeping unresolved names as forward refs."""
    if annotationlib is None:
        try:
            return dict(inspect.get_annotations(obj))
        except Exception:
            return {}
    try:
        return dict(annotationlib.get_annotations(obj, format=annotationlib.Format.FORWARDREF))
    except Exception:
        return {}


def get_hints_for_method(fn: Any) -> dict[str, Any]:
    """Return resolved type hints for *fn*, unwrapping descriptors and wrappers first; ``{}`` on failure.

    Falls back to evaluating with builtins in scope, then to the raw
    ``__annotations__``.
    """
    return hints_of(fn)


def get_raw_params(
    cls: type, method_name: str
) -> tuple[list[inspect.Parameter] | None, dict[str, Any]]:
    """Return ``(params, hints)`` for a method defined directly on *cls*, receiver excluded.

    The receiver is the first positional parameter of an instance method,
    a classmethod or ``__new__``, whatever its name.  ``params`` is ``None``
    when *method_name* is not in ``cls.__dict__`` or has no inspectable
    signature.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return None, {}

    sig = signature_of(unwrap_descriptor(raw))
    if sig is None:
        return None, {}

    params = list(sig.parameters.values())
    has_receiver = not isinstance(raw, staticmethod) or method_name == "__new__"
    if has_receiver and params and params[0].kind in (POS_ONLY, POS_KW):
        params = params[1:]
    elif not has_receiver:
        params = [p for p in params if p.name not in ("self", "cls")]
    return params, get_hints_for_method(raw)
