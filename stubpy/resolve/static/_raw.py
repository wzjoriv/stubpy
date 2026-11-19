"""
``inspect.Parameter`` objects built from harvested source parameters.
"""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy.analysis.harvest.models import FunctionInfo, NonLiteralDefault, RawParam

from .index import SourceModule

_KINDS = {
    "POSITIONAL_ONLY": inspect.Parameter.POSITIONAL_ONLY,
    "POSITIONAL_OR_KEYWORD": inspect.Parameter.POSITIONAL_OR_KEYWORD,
    "VAR_POSITIONAL": inspect.Parameter.VAR_POSITIONAL,
    "KEYWORD_ONLY": inspect.Parameter.KEYWORD_ONLY,
    "VAR_KEYWORD": inspect.Parameter.VAR_KEYWORD,
}


class SourceHints(dict):
    """Empty hints marking parameters whose annotation and default are source text written in *module*."""

    def __init__(self, module: SourceModule | None = None) -> None:
        super().__init__()
        self.module = module


def literal_default(text: str) -> Any:
    """Evaluate a literal default, or wrap a non-literal one in :class:`NonLiteralDefault`."""
    try:
        return ast.literal_eval(text)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return NonLiteralDefault(text)


def parameter(rp: RawParam) -> inspect.Parameter:
    """Return the :class:`inspect.Parameter` of one harvested parameter."""
    default: Any = inspect.Parameter.empty if rp.default_repr is None else literal_default(rp.default_repr)
    annotation: Any = rp.annotation_str or rp.inferred_type_str or inspect.Parameter.empty
    kind = _KINDS.get(rp.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return inspect.Parameter(rp.name, kind, default=default, annotation=annotation)


def is_static(info: FunctionInfo) -> bool:
    """True for a ``@staticmethod``."""
    return any(d.rpartition(".")[2] == "staticmethod" for d in info.decorators)


def own_params(info: FunctionInfo, method: bool) -> list[inspect.Parameter]:
    """Return *info*'s parameters; a method's receiver (first positional parameter) is dropped."""
    raw = list(info.raw_params)
    receiver = method and (not is_static(info) or info.name == "__new__")
    if receiver and raw and raw[0].kind in ("POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"):
        raw = raw[1:]
    elif method and not receiver:
        raw = [p for p in raw if p.name not in ("self", "cls")]
    return [parameter(rp) for rp in raw]
