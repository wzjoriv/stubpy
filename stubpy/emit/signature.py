"""Signature assembly: ``/`` and ``*`` separators, parameter strings and ``def`` layout."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from stubpy._constants import (
    KW_ONLY,
    KW_SEP_NAME,
    POS_KW,
    POS_ONLY,
    POS_SEP_NAME,
    UNINFORMATIVE_DEFAULT_TYPES,
    VAR_KW,
    VAR_POS,
)
from stubpy.resolve import ParamWithHints

from .annotations.defaults import NonLiteralDefault


def insert_kw_separator(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Insert a bare ``*`` sentinel before the first keyword-only parameter when there is no ``*args``.

    Examples
    --------
    >>> kw = inspect.Parameter("b", inspect.Parameter.KEYWORD_ONLY)
    >>> pos = inspect.Parameter("a", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> insert_kw_separator([(pos, {}), (kw, {})])[1][0].name
    '__kw_sep__'
    """
    if any(p.kind == VAR_POS for p, _ in params_with_hints):
        return params_with_hints

    kw_indices = [i for i, (p, _) in enumerate(params_with_hints) if p.kind == KW_ONLY]
    if not kw_indices:
        return params_with_hints

    result = list(params_with_hints)
    result.insert(kw_indices[0], (inspect.Parameter(KW_SEP_NAME, VAR_POS), {}))
    return result


def insert_pos_separator(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Insert a bare ``/`` sentinel after the last positional-only parameter (PEP 570).

    Examples
    --------
    >>> a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
    >>> b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> insert_pos_separator([(a, {}), (b, {})])[1][0].name
    '__pos_sep__'
    """
    last_pos_only = -1
    for i, (p, _) in enumerate(params_with_hints):
        if p.kind == POS_ONLY:
            last_pos_only = i

    if last_pos_only < 0:
        return params_with_hints

    result = list(params_with_hints)
    result.insert(last_pos_only + 1, (inspect.Parameter(POS_SEP_NAME, POS_KW), {}))
    return result


def with_separators(params_with_hints: list[ParamWithHints]) -> list[ParamWithHints]:
    """Apply :func:`insert_pos_separator` then :func:`insert_kw_separator`."""
    return insert_kw_separator(insert_pos_separator(params_with_hints))


def raw_key(param: inspect.Parameter) -> str:
    """Return the ``raw_arg_annotations`` key for *param* (``*args`` / ``**kwargs`` prefixed)."""
    if param.kind == VAR_POS:
        return f"*{param.name}"
    if param.kind == VAR_KW:
        return f"**{param.name}"
    return param.name


def infer_default_type(p: inspect.Parameter, covered: dict[str, str]) -> str | None:
    """Infer a type from *p*'s runtime default, unless *covered* already types it."""
    if p.default is inspect.Parameter.empty:
        return None
    if covered and p.name in covered:
        return None
    d = p.default
    if isinstance(d, NonLiteralDefault):
        return None
    if d is None:
        return "None"
    t = type(d).__name__
    return t if t not in UNINFORMATIVE_DEFAULT_TYPES else None


def render_params(
    params_with_hints: list[ParamWithHints],
    format_one: Callable[[inspect.Parameter, dict[str, Any]], str],
) -> list[str]:
    """Render each parameter with *format_one*, turning separator sentinels into ``*`` and ``/``."""
    return [
        "*" if p.name == KW_SEP_NAME
        else "/" if p.name == POS_SEP_NAME
        else format_one(p, h)
        for p, h in params_with_hints
    ]


def join_params_multiline(param_strs: list[str], inner: str) -> str:
    """Join parameters one per line, putting each trailing comma before any ``#`` comment."""
    parts: list[str] = []
    for s in param_strs:
        if "#" in s:
            idx = s.index("#")
            parts.append(f"{s[:idx].rstrip()},  {s[idx:]}")
        else:
            parts.append(s + ",")
    return (f"\n{inner}").join(parts)


def format_def(
    indent: str,
    keyword: str,
    name: str,
    param_strs: list[str],
    ret_part: str,
    n_params: int,
    body: str = "...",
) -> list[str]:
    """Lay out a ``def``: inline for up to two parameters, otherwise one parameter per line."""
    if n_params <= 2:
        sig = f"{indent}{keyword} {name}({', '.join(param_strs)}){ret_part}"
        if body == "...":
            return [f"{sig}: ..."]
        return [f"{sig}:", f"{indent}    {body}"]

    inner = indent + "    "
    lines = [f"{indent}{keyword} {name}(", f"{inner}{join_params_multiline(param_strs, inner)}"]
    if body == "...":
        lines.append(f"{indent}){ret_part}: ...")
    else:
        lines.append(f"{indent}){ret_part}:")
        lines.append(f"{indent}    {body}")
    return lines
