"""Parameter-list transforms shared by the resolution strategies."""
from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from typing import Any

from stubpy._constants import KW_ONLY, POS_KW, POS_ONLY, VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import ConsumedHints, FunctionInfo, NonLiteralDefault

ParamWithHints = tuple[inspect.Parameter, dict[str, Any]]

_KIND_ORDER = {POS_ONLY: 0, POS_KW: 1, VAR_POS: 2, KW_ONLY: 3, VAR_KW: 4}


@dataclass(frozen=True)
class CallSite:
    """How one call binds the target's parameters before ``**kwargs`` fills the rest."""
    positional: int = 0
    forwards_args: bool = False
    unknown_starred: bool = False
    excluded: frozenset[str] = field(default_factory=frozenset)
    forwards_kwargs: bool = True


def call_site(info: FunctionInfo | None, target: str, forwards_args: bool = False) -> CallSite:
    """Return the :class:`CallSite` of the call to *target* recorded in *info*.

    Without *info*, nothing is bound and *forwards_args* says whether
    ``*args`` reaches the target.
    """
    if info is None:
        return CallSite(forwards_args=forwards_args)
    excluded = set(info.kwargs_explicit_names.get(target, ())) | set(info.kwargs_injected)
    forwards_args = target in info.args_forwarded_to or target in info.args_method_targets
    forwards_kwargs = target in info.kwargs_forwarded_to or target in info.kwargs_method_targets
    return CallSite(
        positional=info.kwargs_positional_skips.get(target, 0),
        forwards_args=forwards_args,
        unknown_starred=target in info.kwargs_unknown_starred,
        excluded=frozenset(excluded),
        forwards_kwargs=forwards_kwargs or not forwards_args,
    )


def bind_call_site(resolved: list[ParamWithHints], site: CallSite) -> tuple[list[ParamWithHints], bool]:
    """Return the target parameters left open by *site*, and whether ``**kwargs`` must be kept.

    Positional arguments bind the first positional parameters.  Parameters
    only reachable through ``**kwargs`` become keyword-only; positional-only
    ones are dropped.  A call forwarding only ``*args`` drops the keyword-only ones and makes the
    positional ones positional-only.  An unknown ``*x`` hides the remaining positional parameters, so
    ``**kwargs`` stays.
    """
    out: list[ParamWithHints] = []
    keep_kw = False
    skip = site.positional
    for p, h in resolved:
        if p.kind in (POS_ONLY, POS_KW):
            if skip:
                skip -= 1
                continue
            if site.unknown_starred:
                keep_kw = keep_kw or p.kind == POS_KW
                continue
            if site.forwards_args and not site.forwards_kwargs:
                p = p.replace(kind=POS_ONLY)
            if not site.forwards_args:
                if p.kind == POS_ONLY:
                    continue
                p = p.replace(kind=KW_ONLY)
        elif p.kind == VAR_POS and not site.forwards_args:
            continue
        elif p.kind in (KW_ONLY, VAR_KW) and not site.forwards_kwargs:
            continue
        if p.name in site.excluded:
            continue
        out.append((p, h))
    return out, keep_kw


def consumed_params(info: FunctionInfo | None, seen: set[str]) -> list[ParamWithHints]:
    """Return keyword-only params for keys the body pops from ``**kwargs``, skipping names in *seen*."""
    if info is None:
        return []
    params: list[ParamWithHints] = []
    for name, default_src in info.kwargs_consumed.items():
        if name in seen or not name.isidentifier():
            continue
        default: Any = inspect.Parameter.empty
        if default_src is not None and default_src != "...":
            try:
                default = ast.literal_eval(default_src)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                default = NonLiteralDefault(default_src)
        elif default_src == "...":
            default = NonLiteralDefault("...")
        params.append((inspect.Parameter(name, KW_ONLY, default=default), ConsumedHints()))
        seen.add(name)
    return params


def order_by_kind(params: list[ParamWithHints]) -> list[ParamWithHints]:
    """Stable-sort *params* into a valid kind order: positional, ``*args``, keyword-only, ``**kwargs``."""
    return sorted(params, key=lambda ph: _KIND_ORDER[ph[0].kind])


def has_kind(params: list[inspect.Parameter], kind: Any) -> bool:
    """Return ``True`` if any parameter in *params* is of *kind*."""
    return any(p.kind == kind for p in params)


def resolved_has_kind(resolved: list[ParamWithHints], kind: Any) -> bool:
    """Return ``True`` if any parameter in a resolved list is of *kind*."""
    return any(p.kind == kind for p, _ in resolved)


def concrete_own(params: list[inspect.Parameter], hints: dict[str, Any]) -> list[ParamWithHints]:
    """Return the non-variadic parameters of *params* paired with *hints*."""
    return [(p, hints) for p in params if p.kind not in (VAR_POS, VAR_KW)]


def merge_concrete_params(
    base: list[ParamWithHints],
    seen: set[str],
    source: list[ParamWithHints],
) -> None:
    """Append the non-variadic params of *source* not yet in *seen* to *base*, in place.

    A positional-only parameter makes the positional parameters before it positional-only too; a typed
    ``*args`` of *source* is kept for :func:`finalise_variadics`.  A keyword popped from ``**kwargs`` (:class:`ConsumedHints`) borrows the
    annotation of the same-named parameter, and its default when the pop
    gave none or a non-literal one.
    """
    for p, h in source:
        if p.kind == VAR_POS and not _is_catch_all(p.annotation) and not resolved_has_kind(base, VAR_POS):
            base.append((p, h))
            continue
        if p.kind in (VAR_POS, VAR_KW):
            continue
        if p.name in seen:
            _type_consumed(base, p, h)
            continue
        if p.kind == POS_ONLY:
            base[:] = [(q.replace(kind=POS_ONLY), qh) if q.kind == POS_KW else (q, qh) for q, qh in base]
        base.append((p, h))
        seen.add(p.name)


def _type_consumed(base: list[ParamWithHints], p: inspect.Parameter, h: dict[str, Any]) -> None:
    """Give the consumed placeholder named like *p* in *base* the annotation (and default) of *p*."""
    for i, (q, qh) in enumerate(base):
        if q.name != p.name or not isinstance(qh, ConsumedHints):
            continue
        default = q.default
        if default is inspect.Parameter.empty or isinstance(default, NonLiteralDefault):
            default = p.default
        if default is None and p.default is not None and p.default is not inspect.Parameter.empty:
            return
        base[i] = (q.replace(annotation=p.annotation, default=default), h)
        return


def apply_call_site(
    resolved: list[ParamWithHints],
    ast_info: FunctionInfo,
    target_name: str,
) -> list[ParamWithHints]:
    """Drop the target's params already bound at the call site, positionally or by keyword."""
    forwards = target_name in getattr(ast_info, "args_forwarded_to", [])
    out, _ = bind_call_site(resolved, call_site(ast_info, target_name, forwards))
    return out


def _is_catch_all(annotation: Any) -> bool:
    """True for no annotation, ``Any`` and ``object``, which say nothing about the arguments."""
    if annotation is inspect.Parameter.empty or annotation is Any or annotation is object:
        return True
    return isinstance(annotation, str) and annotation.rpartition(".")[2] in ("Any", "object")


def finalise_variadics(
    merged: list[ParamWithHints],
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    still_var_pos: bool,
    still_var_kw: bool,
) -> list[ParamWithHints]:
    """Order the merged params, make the signature valid, then re-insert ``*args`` and residual ``**kwargs``.

    ``*args`` is kept when unresolved or typed (beyond ``Any`` / ``object``), before the keyword-only params.
    """
    forwarded = next((p for p, _ in merged if p.kind == VAR_POS), None)
    merged = [(p, h) for p, h in merged if p.kind != VAR_POS]
    merged = enforce_signature_validity(order_by_kind(merged))
    pos_param = next((p for p in own_params if p.kind == VAR_POS), None)
    if pos_param is not None:
        is_typed = not _is_catch_all(pos_param.annotation)
        if still_var_pos and not is_typed and forwarded is not None and pos_param.name not in own_hints:
            pos_param = pos_param.replace(annotation=forwarded.annotation)
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
    return order_by_kind(result)


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
