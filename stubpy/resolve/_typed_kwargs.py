"""Constructors and ``**kwargs`` typed by a class body: ``TypedDict``, ``NamedTuple`` and ``Unpack[TD]``."""
from __future__ import annotations

import inspect
import typing
from typing import Any

from stubpy._constants import KW_ONLY, VAR_KW
from stubpy.analysis.harvest.models import NonLiteralDefault

from ._merge import ParamWithHints
from .callables import signature_of


def _is_typeddict(obj: Any) -> bool:
    return isinstance(obj, type) and issubclass(obj, dict) and hasattr(obj, "__required_keys__")


def typeddict_params(td: type) -> list[ParamWithHints]:
    """Return one keyword-only parameter per key of *td*; optional keys default to ``...``."""
    try:
        hints = typing.get_type_hints(td)
    except Exception:
        hints = dict(getattr(td, "__annotations__", {}))
    required = getattr(td, "__required_keys__", frozenset(hints))
    return [
        (inspect.Parameter(name, KW_ONLY, annotation=hint,
                           default=inspect.Parameter.empty if name in required else NonLiteralDefault("...")), {})
        for name, hint in hints.items()
    ]


def class_constructor(cls: type) -> list[ParamWithHints] | None:
    """Return the constructor parameters of a ``TypedDict`` or ``NamedTuple`` class, else ``None``."""
    if _is_typeddict(cls):
        return typeddict_params(cls)
    if issubclass(cls, tuple) and hasattr(cls, "_fields"):
        sig = signature_of(cls)
        return [(p, {}) for p in sig.parameters.values()] if sig is not None else None
    return None


def unpacked_kwargs(params: list[inspect.Parameter], hints: dict[str, Any]) -> list[ParamWithHints] | None:
    """Return *params* with ``**kwargs: Unpack[TD]`` replaced by the keys of ``TD``, or ``None`` without one."""
    kw = next((p for p in params if p.kind == VAR_KW), None)
    if kw is None:
        return None
    annotation = hints.get(kw.name, kw.annotation)
    args = typing.get_args(annotation)
    if getattr(annotation, "__origin__", None) is None or not args or not _is_typeddict(args[0]):
        return None
    origin = annotation.__origin__
    if getattr(origin, "_name", None) != "Unpack" and "Unpack" not in repr(origin):
        return None
    names = {p.name for p in params}
    keys = [(p, h) for p, h in typeddict_params(args[0]) if p.name not in names]
    return [(p, hints) for p in params if p.kind != VAR_KW] + keys
