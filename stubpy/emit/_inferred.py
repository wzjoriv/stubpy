"""
Types inferred where the source has none: safe return types and docstring types of forwarded parameters.
"""
from __future__ import annotations

import functools
from typing import Any

from stubpy._constants import SELF_RETURN
from stubpy.analysis.docstrings import DocstringTypes, parse_docstring_types
from stubpy.analysis.harvest.models import FunctionInfo
from stubpy.analysis.symbols.models import ClassSymbol
from stubpy.resolve import ParamWithHints, unwrap_callable
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Stage

from .annotations.params import is_plain_annotation

_SELF_SINCE = (3, 11)


def inferred_return_text(info: FunctionInfo | None, ctx: StubContext, class_name: str | None = None) -> str:
    """Return the safe return type harvested for *info*, or ``""`` when there is none or it does not apply here."""
    found = getattr(info, "raw_inferred_return", None)
    if not found:
        return ""
    if found == SELF_RETURN:
        if class_name is None:
            return ""
        return SELF_RETURN if ctx.config.target_version >= _SELF_SINCE else class_name
    named = getattr(info, "inferred_return_class", None)
    if named is not None:
        table = ctx.symbol_table
        known = table is not None and isinstance(table.get(named), ClassSymbol)
        return named if known or named == class_name else ""
    return found


def documented_types(fn: Any, info: FunctionInfo | None, ctx: StubContext, report: bool = True) -> DocstringTypes:
    """The docstring types of *fn* (or, without a live object, of its source *info*) under ``infer_types``.

    The return type is kept only when it is a plain annotation (builtins and ``typing`` names).
    """
    if not ctx.config.infer_types:
        return DocstringTypes()
    doc = getattr(fn, "__doc__", None) if fn is not None else None
    if not isinstance(doc, str) or not doc.strip():
        doc = info.docstring if info is not None else None
    parsed = parse_docstring_types(doc)
    loose = [f"{k}: {v}" for k, v in parsed.params.items() if not is_plain_annotation(v)]
    if parsed.returns and not is_plain_annotation(parsed.returns):
        loose.append(f"return: {parsed.returns}")
        parsed = DocstringTypes(parsed.params, None)
    filled = len(parsed.params) - sum(not t.startswith("return: ") for t in loose) + (parsed.returns is not None)
    if report and (filled or loose):
        name = info.name if info is not None else getattr(fn, "__qualname__", "?")
        note = f"Docstring types: {filled} filled"
        if loose:
            note += f"; kept as comments (not plain annotations): {', '.join(loose)}"
        ctx.diagnostics.info(Stage.EMIT, name, note)
    return parsed


@functools.lru_cache(maxsize=256)
def _documented(doc: str) -> dict[str, str]:
    return {k: v for k, v in parse_docstring_types(doc).params.items() if is_plain_annotation(v)}


def _owner_class(fn: Any) -> Any:
    """Return the class an ``__init__`` belongs to, looked up by qualified name in its module."""
    if getattr(fn, "__name__", "") != "__init__":
        return None
    obj: Any = getattr(fn, "__globals__", {})
    for part in getattr(fn, "__qualname__", "").split(".")[:-1]:
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
    return obj if isinstance(obj, type) else None


def _callee_types(owner: Any) -> dict[str, str]:
    """Return the plain parameter types documented by *owner* (and, for ``__init__``, by its class)."""
    types: dict[str, str] = {}
    for source in (owner, _owner_class(owner)):
        doc = getattr(source, "__doc__", None) if source is not None else None
        if isinstance(doc, str) and doc.strip():
            for name, text in _documented(doc).items():
                types.setdefault(name, text)
    return types


def with_callee_types(
    params: list[ParamWithHints], own: Any, info: FunctionInfo | None, types: dict[str, str],
) -> dict[str, str]:
    """Return *types* plus the docstring types of parameters forwarded from another callable.

    Only types made of builtins and ``typing`` names are taken; parameters of *own* itself are
    left to ``infer_types``.
    """
    own_fn = unwrap_callable(own) if own is not None else None
    own_names = {rp.name for rp in info.raw_params} if info is not None else set()
    out = dict(types)
    for p, hints in params:
        owner = getattr(hints, "owner", None)
        if owner is None or p.name in out or p.name in own_names or unwrap_callable(owner) is own_fn:
            continue
        found = _callee_types(owner).get(p.name)
        if found:
            out[p.name] = found
    return out
