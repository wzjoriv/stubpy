"""Module attributes bound to ``functools.partial``: a ``def`` with the parameters left open."""
from __future__ import annotations

import ast
import functools
import sys
from typing import Any

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.core.context import StubContext
from stubpy.resolve import ParamWithHints, function_info_of, resolve_function_params, resolve_params

from .annotations import format_param
from .annotations.defaults import name_in_scope
from .annotations.source import hint_text
from .signature import format_def, render_params, with_separators


def _target_params(func: Any) -> list[ParamWithHints]:
    """Return the resolved parameters of the partial's target (a class's ``__init__`` or a function)."""
    if isinstance(func, type):
        module = sys.modules.get(func.__module__)
        return resolve_params(func, "__init__", namespace=vars(module) if module is not None else None)
    namespace = getattr(func, "__globals__", None) or {}
    return resolve_function_params(func, function_info_of(func), namespace)


def bind_partial(params: list[ParamWithHints], args: tuple, keywords: dict[str, Any]) -> list[ParamWithHints]:
    """Apply a partial's bound *args* and *keywords* to *params*, as :func:`inspect.signature` does.

    Positional arguments remove the first positional parameters; a keyword
    gives its parameter a new default and makes it and every later
    positional parameter keyword-only.
    """
    out: list[ParamWithHints] = []
    skip = len(args)
    keyword_seen = False
    for p, h in params:
        if p.kind in (POS_ONLY, POS_KW) and skip:
            skip -= 1
            continue
        if p.kind == VAR_POS and args and skip:
            continue
        if p.name in keywords and p.kind not in (VAR_POS, VAR_KW):
            p = p.replace(kind=KW_ONLY, default=keywords[p.name])
            keyword_seen = True
        elif keyword_seen and p.kind == POS_KW:
            p = p.replace(kind=KW_ONLY)
        out.append((p, h))
    return out


def generate_partial_stub(name: str, value: functools.partial, ctx: StubContext) -> str:
    """Return ``def name(<open parameters>) -> R: ...`` for ``name = partial(target, ...)``.

    ``R`` is the target class, or the target function's return annotation.
    """
    func = value.func
    params = with_separators(bind_partial(_target_params(func), value.args, value.keywords))
    param_strs = render_params(params, lambda p, h: format_param(p, h, ctx))
    ret = (name_in_scope(func, ctx) or "") if isinstance(func, type) else hint_text(func, "return", ctx)
    return "\n".join(format_def("", "def", name, param_strs, f" -> {ret}" if ret else "", len(param_strs)))


def partial_annotation(value_repr: str | None) -> str | None:
    """Return ``partial[T]`` for an AST-only ``partial(T, ...)`` right-hand side naming a class, else ``partial[Any]``.

    ``None`` when the right-hand side is not a ``partial`` call.

    Examples
    --------
    >>> partial_annotation("functools.partial(Length, unit=Unit.PX)")
    'partial[Length]'
    >>> partial_annotation("partial(rect, fill='none')")
    'partial[Any]'
    """
    try:
        node = ast.parse(value_repr or "", mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    callee = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    if callee != "partial":
        return None
    target = node.args[0]
    if isinstance(target, ast.Name) and target.id[:1].isupper():
        return f"partial[{target.id}]"
    return "partial[Any]"
