"""Parameter-list transforms shared by the resolution strategies."""
from __future__ import annotations

import inspect
from typing import Any

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

ParamWithHints = tuple[inspect.Parameter, dict[str, Any]]


def has_kind(params: list[inspect.Parameter], kind: Any) -> bool:
    """Return ``True`` if any parameter in *params* is of *kind*."""
    return any(p.kind == kind for p in params)


def resolved_has_kind(resolved: list[ParamWithHints], kind: Any) -> bool:
    """Return ``True`` if any parameter in a resolved list is of *kind*."""
    return any(p.kind == kind for p, _ in resolved)


def normalise_kind(p: inspect.Parameter) -> inspect.Parameter:
    """Promote ``POSITIONAL_ONLY`` to ``POSITIONAL_OR_KEYWORD`` for params absorbed by ``**kwargs``."""
    if p.kind == POS_ONLY:
        return p.replace(kind=POS_KW)
    return p


def concrete_own(params: list[inspect.Parameter], hints: dict[str, Any]) -> list[ParamWithHints]:
    """Return the non-variadic parameters of *params* paired with *hints*."""
    return [(p, hints) for p in params if p.kind not in (VAR_POS, VAR_KW)]


def merge_concrete_params(
    base: list[ParamWithHints],
    seen: set[str],
    source: list[ParamWithHints],
) -> None:
    """Append the non-variadic params of *source* not yet in *seen* to *base*, in place."""
    for p, h in source:
        if p.kind in (VAR_POS, VAR_KW):
            continue
        if p.name in seen:
            continue
        base.append((normalise_kind(p), h))
        seen.add(p.name)


def apply_call_site(
    resolved: list[ParamWithHints],
    ast_info: FunctionInfo,
    target_name: str,
) -> list[ParamWithHints]:
    """Drop the target's params already bound at the call site, positionally or by keyword."""
    if target_name in getattr(ast_info, "kwargs_positional_skips", {}):
        skip_n = ast_info.kwargs_positional_skips[target_name]
        non_var = [(p, h) for p, h in resolved if p.kind not in (VAR_POS, VAR_KW)]
        variadics = [(p, h) for p, h in resolved if p.kind in (VAR_POS, VAR_KW)]
        resolved = non_var[skip_n:] + variadics
    if target_name in getattr(ast_info, "kwargs_explicit_names", {}):
        excl = ast_info.kwargs_explicit_names[target_name]
        resolved = [(p, h) for p, h in resolved if p.name not in excl]
    return resolved


def finalise_variadics(
    merged: list[ParamWithHints],
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    still_var_pos: bool,
    still_var_kw: bool,
) -> list[ParamWithHints]:
    """Re-insert ``*args`` (if unresolved or typed) before keyword-only params and append residual ``**kwargs``."""
    pos_param = next((p for p in own_params if p.kind == VAR_POS), None)
    if pos_param is not None:
        is_typed = pos_param.annotation is not inspect.Parameter.empty
        if still_var_pos or is_typed:
            insert_at = next(
                (i for i, (p, _) in enumerate(merged) if p.kind in (KW_ONLY, VAR_KW)),
                len(merged),
            )
            merged.insert(insert_at, (pos_param, own_hints))

    if still_var_kw:
        kw_param = next((p for p in own_params if p.kind == VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged


def enforce_signature_validity(merged: list[ParamWithHints]) -> list[ParamWithHints]:
    """Make required params that follow a defaulted one ``KEYWORD_ONLY``, keeping the signature valid.

    For example ``make_red(r=1.0, g, b)`` becomes ``make_red(r=1.0, *, g, b)``.
    """
    first_default_idx: int | None = None
    for i, (p, _) in enumerate(merged):
        if p.kind in (VAR_POS, VAR_KW):
            continue
        if p.default is not inspect.Parameter.empty:
            first_default_idx = i
            break

    if first_default_idx is None:
        return merged

    result: list[ParamWithHints] = []
    for i, (p, h) in enumerate(merged):
        if (
            i > first_default_idx
            and p.kind not in (VAR_POS, VAR_KW, KW_ONLY)
            and p.default is inspect.Parameter.empty
        ):
            p = p.replace(kind=KW_ONLY)
        result.append((p, h))
    return result
