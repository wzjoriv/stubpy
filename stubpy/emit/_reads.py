"""
Parameters for keys the body reads from ``**kwargs`` / ``*args``, and the selector of a dispatch variant.
"""
from __future__ import annotations

import ast
import inspect
from typing import Any

from stubpy._constants import READ_LITERAL_TYPES
from stubpy.analysis.harvest.models import FunctionInfo, NonLiteralDefault
from stubpy.resolve import ParamWithHints

_P = inspect.Parameter


def _read_param(name: str, default_src: str | None, kind: Any) -> ParamWithHints:
    """A parameter for one read key: typed from a literal default, else ``Any``."""
    if default_src is None:
        return _P(name, kind, annotation=Any), {}
    try:
        default = ast.literal_eval(default_src)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _P(name, kind, default=NonLiteralDefault(default_src), annotation=Any), {}
    annotation = READ_LITERAL_TYPES.get(type(default), Any)
    return _P(name, kind, default=default, annotation=annotation), {}


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

    A key read from ``**kwargs`` becomes keyword-only (typed from a literal
    ``.get`` default, else ``Any``) unless a forwarded callee already gave
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
        reads = [_read_param(k, d, _P.KEYWORD_ONLY) for k, d in info.kwargs_read.items() if k not in names]
        at = next((i for i, (p, _) in enumerate(params) if p.kind == _P.VAR_KEYWORD), len(params))
        params = params[:at] + reads + params[at:]
    return _with_args_reads(params, info)
