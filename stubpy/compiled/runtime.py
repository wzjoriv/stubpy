"""Compiled signatures as :class:`inspect.Signature` objects, for back-tracing ``**kwargs`` into compiled code."""
from __future__ import annotations

import ast
import inspect
import types
from typing import Any

from stubpy._constants import POS_ONLY
from stubpy.analysis.harvest.models import NonLiteralDefault

from .detect import SLOT_WRAPPER_TYPES, is_compiled_callable
from .signatures import Param, Signature, class_signatures, signatures_of
from .typemap import portable_annotation

__all__ = ["compiled_signatures", "compiled_signature", "overload_count"]

_CONSTRUCTOR_TYPES = (*SLOT_WRAPPER_TYPES, types.BuiltinFunctionType)


def _owner_class(obj: Any) -> type | None:
    """The class whose slot-wrapper ``__init__`` / ``__new__`` *obj* is."""
    if getattr(obj, "__name__", "") not in ("__init__", "__new__") or not isinstance(obj, _CONSTRUCTOR_TYPES):
        return None
    owner = getattr(obj, "__objclass__", None) or getattr(obj, "__self__", None)
    return owner if isinstance(owner, type) and owner is not object else None


def compiled_signatures(obj: Any) -> list[Signature]:
    """Every signature of a compiled callable; a slot-wrapper constructor uses its class's own signature.

    Constructor signatures from the class come back with a leading ``self``.
    """
    if not is_compiled_callable(obj):
        return []
    owner = _owner_class(obj)
    if owner is not None:
        found = class_signatures(owner)
        if found:
            return [Signature((Param("self", POS_ONLY), *s.params), s.returns) for s in found]
    return [s for s in signatures_of(obj) if not s.is_generic()]


def overload_count(obj: Any) -> int:
    """How many signatures a compiled callable has (0 when it is not compiled or has none)."""
    return len(compiled_signatures(obj))


def _default(text: str | None) -> Any:
    if text is None:
        return inspect.Parameter.empty
    try:
        return ast.literal_eval(text)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return NonLiteralDefault(text)


def compiled_signature(obj: Any) -> inspect.Signature | None:
    """The single signature of a compiled callable as an :class:`inspect.Signature`; ``None`` when it has 0 or several.

    Annotations are strings, kept only when they need no import
    (builtins, ``typing``, ``collections.abc``).
    """
    found = compiled_signatures(obj)
    if len(found) != 1:
        return None
    sig = found[0]
    try:
        params = [
            inspect.Parameter(p.name, p.kind, default=_default(p.default),
                              annotation=portable_annotation(p.annotation) or inspect.Parameter.empty)
            for p in sig.params
        ]
        returns = portable_annotation(sig.returns) or inspect.Signature.empty
        return inspect.Signature(params, return_annotation=returns)
    except (TypeError, ValueError):
        return None
