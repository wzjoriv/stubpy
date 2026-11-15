"""Module attributes bound to ``functools.partial``: a ``def`` with the parameters left open."""
from __future__ import annotations

import ast
import functools
import sys
from typing import Any

from stubpy.core.context import StubContext
from stubpy.resolve import (
    ParamWithHints,
    bind_partial,
    function_info_of,
    resolve_function_params,
    resolve_params,
)

from ._static import static_partial
from .annotations import format_param
from .annotations.defaults import name_in_scope
from .annotations.source import hint_text
from .annotations.style import style_text
from .signature import format_def, render_params, with_separators


def _target_params(func: Any) -> list[ParamWithHints]:
    """Return the resolved parameters of the partial's target (a class's ``__init__`` or a function)."""
    if isinstance(func, type):
        module = sys.modules.get(func.__module__)
        return resolve_params(func, "__init__", namespace=vars(module) if module is not None else None)
    namespace = getattr(func, "__globals__", None) or {}
    return resolve_function_params(func, function_info_of(func), namespace)


def generate_partial_stub(name: str, value: functools.partial, ctx: StubContext) -> str:
    """Return ``def name(<open parameters>) -> R: ...`` for ``name = partial(target, ...)``.

    ``R`` is the target class, or the target function's return annotation.
    """
    func = value.func
    params = with_separators(bind_partial(_target_params(func), value.args, value.keywords))
    param_strs = render_params(params, lambda p, h: format_param(p, h, ctx))
    ret = (name_in_scope(func, ctx) or "") if isinstance(func, type) else hint_text(func, "return", ctx)
    return "\n".join(format_def("", "def", name, param_strs, f" -> {ret}" if ret else "", len(param_strs)))


def generate_static_partial_stub(name: str, value_repr: str, ctx: StubContext) -> str | None:
    """Return the ``def`` of an AST-only ``name = partial(target, ...)`` whose target is in the source index."""
    found = static_partial(value_repr, ctx)
    if found is None:
        return None
    params, ret = found
    param_strs = render_params(with_separators(params), lambda p, h: format_param(p, h, ctx))
    ret_part = f" -> {style_text(ret, ctx)}" if ret else ""
    return "\n".join(format_def("", "def", name, param_strs, ret_part, len(param_strs)))


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
