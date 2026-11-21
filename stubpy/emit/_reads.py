"""
Parameters for keys the body reads from ``**kwargs`` / ``*args``, and the selector of a dispatch variant.
"""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy.analysis.harvest.models import FunctionInfo, NonLiteralDefault
from stubpy.emit._constants import READ_LITERAL_TYPES
from stubpy.resolve import ParamWithHints

_P = inspect.Parameter


def _typed(annotation: Any, default: Any) -> Any:
    """*annotation* widened with ``None`` when the read's default is ``None``."""
    if default is not None or annotation is Any or annotation is None:
        return annotation
    if isinstance(annotation, str):
        return annotation if "None" in annotation or annotation == "Any" else f"{annotation} | None"
    try:
        return annotation | None
    except TypeError:
        return Any


def _read_param(name: str, default_src: str | None, kind: Any, typed: Any = _P.empty) -> ParamWithHints:
    """A parameter for one read key: typed from ``**kwargs: T``, else from a literal default, else ``Any``."""
    if typed is not _P.empty:
        param, hints = _read_param(name, default_src, kind)
        return param.replace(annotation=_typed(typed, param.default)), hints
    if default_src is None:
        return _P(name, kind, annotation=Any), {}
    try:
        default = ast.literal_eval(default_src)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _P(name, kind, default=NonLiteralDefault(default_src), annotation=Any), {}
    annotation = READ_LITERAL_TYPES.get(type(default), Any)
    return _P(name, kind, default=default, annotation=annotation), {}


def _with_sliced_args(params: list[ParamWithHints], info: FunctionInfo) -> list[ParamWithHints]:
    """For ``f(*args[k:])``, insert ``args_0`` ... ``args_{k-1}`` (not forwarded) before the expanded parameters.

    Only when the forward expanded (a target parameter follows the function's own); those stay first,
    positional-only.
    """
    if not info.args_sliced:
        return params
    own = {rp.name for rp in info.raw_params}
    at = next((i for i, (p, _) in enumerate(params) if p.name not in own or p.kind != _P.POSITIONAL_OR_KEYWORD
               and p.kind != _P.POSITIONAL_ONLY), len(params))
    if at == len(params) or params[at][0].kind not in (_P.POSITIONAL_ONLY, _P.POSITIONAL_OR_KEYWORD):
        return params
    star = next((rp.name for rp in info.raw_params if rp.kind == "VAR_POSITIONAL"), "args")
    names = {p.name for p, _ in params}
    head = [(p.replace(kind=_P.POSITIONAL_ONLY) if p.kind == _P.POSITIONAL_OR_KEYWORD else p, h)
            for p, h in params[:at]]
    added = [(_P(f"{star}_{i}", _P.POSITIONAL_ONLY, annotation=Any), {}) for i in range(info.args_sliced)
             if f"{star}_{i}" not in names]
    if head and any(p.default is not _P.empty for p, _ in head):
        return params
    return head + added + params[at:]


def _with_args_reads(params: list[ParamWithHints], info: FunctionInfo) -> list[ParamWithHints]:
    """Insert one positional-only parameter per ``args[i]`` read before an unforwarded ``*args``."""
    at = next((i for i, (p, _) in enumerate(params) if p.kind == _P.VAR_POSITIONAL), None)
    if at is None or not info.args_read or info.args_forwarded_to or info.args_method_targets:
        return params
    star = params[at][0].name
    names = {p.name for p, _ in params}
    head = [(p.replace(kind=_P.POSITIONAL_ONLY) if p.kind == _P.POSITIONAL_OR_KEYWORD else p, h)
            for p, h in params[:at]]
    optional = any(p.default is not _P.empty for p, _ in head)
    added = []
    for i in range(info.args_read):
        name = f"{star}_{i}"
        if name in names:
            return params
        default = NonLiteralDefault("...") if optional else _P.empty
        added.append((_P(name, _P.POSITIONAL_ONLY, default=default, annotation=Any), {}))
    return head + added + params[at:]


def _narrowed(params: list[ParamWithHints], selector: str, annotation: str) -> list[ParamWithHints]:
    """*params* with *selector* annotated *annotation*, keeping its default only when the variant allows it."""
    out = []
    for p, h in params:
        if p.name == selector:
            default = p.default
            if default is not _P.empty and repr(default) not in annotation:
                optional = any(q.default is not _P.empty for q, _ in out if q.kind != _P.KEYWORD_ONLY)
                default = NonLiteralDefault("...") if optional and p.kind != _P.KEYWORD_ONLY else _P.empty
            p, h = p.replace(annotation=annotation, default=default), {}
        out.append((p, h))
    return out


def with_reads(params: list[ParamWithHints], info: FunctionInfo | None) -> list[ParamWithHints]:
    """Add the parameters *info*'s body reads from its variadics, and narrow a dispatch variant's selector.

    A key read from ``**kwargs`` becomes keyword-only (typed ``T`` under
    ``**kwargs: T``, else from a literal ``.get`` default, else ``Any``) unless a forwarded callee already gave
    that name; ``args[i]`` reads become positional-only when ``*args`` is not
    forwarded.

    Parameters
    ----------
    params : list of tuple of (inspect.Parameter, dict)
        The resolved parameters, without the receiver.
    info : FunctionInfo or None
        The harvested function; ``None`` leaves *params* unchanged.

    Returns
    -------
    list of tuple of (inspect.Parameter, dict)
        The parameters with the reads added.

    Examples
    --------
    >>> from stubpy.analysis.harvest import ast_harvest
    >>> info = ast_harvest("def f(**kw):\\n    return kw.get('size', 3)").functions[0]
    >>> kw = inspect.Parameter("kw", inspect.Parameter.VAR_KEYWORD)
    >>> [(p.name, p.default) for p, _ in with_reads([(kw, {})], info)][0]
    ('size', 3)
    """
    if info is None:
        return params
    if info.selected is not None:
        params = _narrowed(params, *info.selected)
    if info.kwargs_read:
        names = {p.name for p, _ in params}
        at = next((i for i, (p, _) in enumerate(params) if p.kind == _P.VAR_KEYWORD), len(params))
        typed = params[at][0].annotation if at < len(params) else _P.empty
        reads = [_read_param(k, d, _P.KEYWORD_ONLY, typed) for k, d in info.kwargs_read.items() if k not in names]
        params = params[:at] + reads + params[at:]
    return _with_sliced_args(_with_args_reads(params, info), info)
