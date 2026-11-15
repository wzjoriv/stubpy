"""``**kwargs`` / ``*args`` backtracing for methods and module-level functions.

:func:`resolve_params` resolves a method through ``cls(...)`` calls, the
class MRO and then module-level forwarding targets; :func:`resolve_function_params`
resolves a standalone function through its forwarding targets.  The two call
each other for mixed chains, with a ``_seen`` set guarding against cycles.
"""
from __future__ import annotations

import inspect
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

from ._cls_call import detect_cls_call, merge_with_init
from ._merge import (
    ParamWithHints,
    apply_call_site,
    concrete_own,
    enforce_signature_validity,
    finalise_variadics,
    has_kind,
    merge_concrete_params,
    resolved_has_kind,
)
from ._mro import walk_mro
from .hints import get_hints_for_method, get_raw_params


def resolve_params(
    cls: type,
    method_name: str,
    ast_info: FunctionInfo | None = None,
    namespace: dict[str, Any] | None = None,
    ast_info_by_name: dict[str, FunctionInfo] | None = None,
    _seen: frozenset[str] | None = None,
) -> list[ParamWithHints]:
    """Return the parameters of *method_name* on *cls* with its variadics expanded.

    Strategies, in order: no variadics (own params unchanged); a classmethod
    calling ``cls(..., **kwargs)`` resolves against ``cls.__init__``; the
    MRO walk; then module-level forwarding targets found in *namespace*.
    ``self`` / ``cls`` are excluded from the result.

    Examples
    --------
    >>> class Base:
    ...     def __init__(self, color: str, opacity: float = 1.0) -> None: ...
    >>> class Child(Base):
    ...     def __init__(self, label: str, **kwargs) -> None: ...
    >>> [p.name for p, _ in resolve_params(Child, "__init__")]
    ['label', 'color', 'opacity']
    """
    own_params, own_hints = get_raw_params(cls, method_name)

    if own_params is None:
        for parent in cls.__mro__[1:]:
            if method_name in parent.__dict__:
                return resolve_params(
                    parent, method_name,
                    namespace=namespace,
                    ast_info_by_name=ast_info_by_name,
                    _seen=_seen,
                )
        return []

    has_var_kw = has_kind(own_params, VAR_KW)
    has_var_pos = has_kind(own_params, VAR_POS)

    if not has_var_kw and not has_var_pos:
        return [(p, own_hints) for p in own_params]

    if isinstance(cls.__dict__.get(method_name), classmethod) and has_var_kw:
        found, explicit_kw = detect_cls_call(cls, method_name, ast_info)
        if found:
            return merge_with_init(own_params, own_hints, explicit_kw, resolve_params(cls, "__init__"))

    if _seen is None:
        _seen = frozenset({f"{cls.__name__}.{method_name}"})

    merged = concrete_own(own_params, own_hints)
    seen_names = {p.name for p, _ in merged}
    still_var_kw, still_var_pos = walk_mro(
        cls, method_name, merged, seen_names, has_var_kw, has_var_pos,
    )

    if (still_var_kw or still_var_pos) and namespace and ast_info is not None:
        still_var_kw, still_var_pos = _resolve_via_namespace(
            cls, ast_info, namespace, ast_info_by_name, _seen,
            merged, seen_names, still_var_kw, still_var_pos,
        )

    merged = enforce_signature_validity(merged)
    return finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)


def resolve_function_params(
    live_fn: Any,
    ast_info: FunctionInfo | None,
    namespace: dict[str, Any],
    *,
    ast_info_by_name: dict[str, FunctionInfo] | None = None,
    _seen: frozenset[str] | None = None,
) -> list[ParamWithHints]:
    """Return the parameters of a module-level function with its variadics expanded.

    Each forwarding target recorded in *ast_info* is looked up in
    *namespace*; class targets resolve through their ``__init__``.  Absorbed
    positional-only params become positional-or-keyword, and ``*args`` /
    residual ``**kwargs`` are kept when unresolved.
    """
    if live_fn is None:
        return []

    try:
        own_params = list(inspect.signature(live_fn).parameters.values())
    except (ValueError, TypeError):
        return []

    own_hints = get_hints_for_method(live_fn)
    has_var_kw = has_kind(own_params, VAR_KW)
    has_var_pos = has_kind(own_params, VAR_POS)

    if (not has_var_kw and not has_var_pos) or ast_info is None:
        return [(p, own_hints) for p in own_params]

    kw_targets = ast_info.kwargs_forwarded_to if has_var_kw else []
    pos_targets = ast_info.args_forwarded_to if has_var_pos else []

    if not kw_targets and not pos_targets:
        return [(p, own_hints) for p in own_params]

    fn_name = getattr(live_fn, "__name__", None) or getattr(live_fn, "__qualname__", None)
    if _seen is None:
        _seen = frozenset()
    _seen = _seen | {fn_name} if fn_name else _seen

    merged = concrete_own(own_params, own_hints)
    seen_names = {p.name for p, _ in merged}

    still_var_kw, still_var_pos = _resolve_targets(
        _dedupe(kw_targets + pos_targets), kw_targets, pos_targets,
        ast_info, namespace, ast_info_by_name, _seen,
        merged, seen_names, has_var_kw, has_var_pos,
    )

    merged = enforce_signature_validity(merged)
    return finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)


def _dedupe(names: list[str], skip: tuple[str, ...] = ()) -> list[str]:
    """Return *names* without duplicates or *skip* entries, keeping order."""
    out: list[str] = []
    for n in names:
        if n not in out and n not in skip:
            out.append(n)
    return out


def _resolve_targets(
    names: list[str],
    kw_targets: list[str],
    pos_targets: list[str],
    ast_info: FunctionInfo,
    namespace: dict[str, Any],
    ast_info_by_name: dict[str, FunctionInfo] | None,
    _seen: frozenset[str],
    merged: list[ParamWithHints],
    seen_names: set[str],
    still_var_kw: bool,
    still_var_pos: bool,
) -> tuple[bool, bool]:
    """Merge the params of each namespace target in *names*; return the updated variadic flags."""
    for target_name in names:
        if target_name in _seen:
            continue

        target = namespace.get(target_name)
        if target is None:
            continue

        inner_seen = _seen | {target_name}
        if isinstance(target, type):
            resolved = resolve_params(
                target, "__init__",
                namespace=namespace,
                ast_info_by_name=ast_info_by_name,
                _seen=inner_seen,
            )
        else:
            if not callable(target):
                continue
            try:
                target_params = list(inspect.signature(target).parameters.values())
            except (ValueError, TypeError):
                continue

            if has_kind(target_params, VAR_KW) or has_kind(target_params, VAR_POS):
                resolved = resolve_function_params(
                    target, (ast_info_by_name or {}).get(target_name), namespace,
                    ast_info_by_name=ast_info_by_name,
                    _seen=inner_seen,
                )
            else:
                t_hints = get_hints_for_method(target)
                resolved = [(p, t_hints) for p in target_params]
            resolved = apply_call_site(resolved, ast_info, target_name)

        merge_concrete_params(merged, seen_names, resolved)
        if target_name in kw_targets and not resolved_has_kind(resolved, VAR_KW):
            still_var_kw = False
        if target_name in pos_targets and not resolved_has_kind(resolved, VAR_POS):
            still_var_pos = False

    return still_var_kw, still_var_pos


def _resolve_via_namespace(
    cls: type,
    ast_info: FunctionInfo,
    namespace: dict[str, Any],
    ast_info_by_name: dict[str, FunctionInfo] | None,
    _seen: frozenset[str],
    merged: list[ParamWithHints],
    seen_names: set[str],
    still_var_kw: bool,
    still_var_pos: bool,
) -> tuple[bool, bool]:
    """Resolve a method's leftover variadics via module functions, then ``self.X`` / ``cls.X`` calls."""
    kw_targets = ast_info.kwargs_forwarded_to if still_var_kw else []
    pos_targets = ast_info.args_forwarded_to if still_var_pos else []

    still_var_kw, still_var_pos = _resolve_targets(
        _dedupe(kw_targets + pos_targets, skip=("cls", "self")), kw_targets, pos_targets,
        ast_info, namespace, ast_info_by_name, _seen,
        merged, seen_names, still_var_kw, still_var_pos,
    )

    method_kw_targets = getattr(ast_info, "kwargs_method_targets", [])
    method_pos_targets = getattr(ast_info, "args_method_targets", [])
    for target_name in method_kw_targets + method_pos_targets:
        if target_name in _seen:
            continue
        resolved = resolve_params(
            cls, target_name,
            namespace=namespace,
            ast_info_by_name=ast_info_by_name,
            _seen=_seen | {target_name},
        )
        if not resolved:
            continue

        resolved = apply_call_site(resolved, ast_info, target_name)
        merge_concrete_params(merged, seen_names, resolved)
        if target_name in method_kw_targets and not resolved_has_kind(resolved, VAR_KW):
            still_var_kw = False
        if target_name in method_pos_targets and not resolved_has_kind(resolved, VAR_POS):
            still_var_pos = False

    return still_var_kw, still_var_pos
