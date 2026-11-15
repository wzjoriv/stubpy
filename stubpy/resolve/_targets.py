"""Forwarding targets of ``**kwargs`` / ``*args``: module functions, classes and ``self.X`` / ``cls.X`` methods."""
from __future__ import annotations

import sys
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

from ._merge import (
    ParamWithHints,
    bind_call_site,
    call_site,
    has_kind,
    merge_concrete_params,
    resolved_has_kind,
)
from .callables import signature_of, unwrap_callable
from .hints import get_hints_for_method


def dedupe(names: list[str], skip: tuple[str, ...] = ()) -> list[str]:
    """Return *names* without duplicates or *skip* entries, keeping order."""
    out: list[str] = []
    for n in names:
        if n not in out and n not in skip:
            out.append(n)
    return out


def _home(obj: Any, namespace: dict[str, Any], ast_info_by_name: dict[str, FunctionInfo] | None,
          ) -> tuple[dict[str, Any], dict[str, FunctionInfo] | None]:
    """Return the namespace *obj* was defined in, with the AST infos only when it is *namespace* itself."""
    if isinstance(obj, type):
        module = sys.modules.get(getattr(obj, "__module__", "") or "")
        home = vars(module) if module is not None else None
    else:
        home = getattr(unwrap_callable(obj), "__globals__", None)
    if not isinstance(home, dict) or home is namespace:
        return namespace, ast_info_by_name
    return home, None


def _target_params(
    target_name: str,
    namespace: dict[str, Any],
    ast_info_by_name: dict[str, FunctionInfo] | None,
    inner_seen: frozenset[str],
) -> list[ParamWithHints] | None:
    """Return the resolved params of a namespace target, or ``None`` when it cannot be inspected.

    Targets defined in another module resolve their own forwarding in that module's namespace.
    """
    from .params import resolve_function_params, resolve_params

    if "." in target_name:
        owner_name, _, method = target_name.partition(".")
        owner = namespace.get(owner_name.removesuffix("()"))
        if not isinstance(owner, type):
            return None
        ns, infos = _home(owner, namespace, ast_info_by_name)
        return resolve_params(owner, method, namespace=ns, ast_info_by_name=infos, _seen=inner_seen)

    target = namespace.get(target_name)
    if target is None:
        return None
    ns, infos = _home(target, namespace, ast_info_by_name)
    if isinstance(target, type):
        return resolve_params(target, "__init__", namespace=ns, ast_info_by_name=infos, _seen=inner_seen)
    if not callable(target):
        return None
    target_sig = signature_of(target)
    if target_sig is None:
        return None
    target_params = list(target_sig.parameters.values())
    if has_kind(target_params, VAR_KW) or has_kind(target_params, VAR_POS):
        return resolve_function_params(
            target, (infos or {}).get(target_name), ns,
            ast_info_by_name=infos,
            _seen=inner_seen,
        )
    t_hints = get_hints_for_method(target)
    return [(p, t_hints) for p in target_params]


def resolve_targets(
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
        resolved = _target_params(target_name, namespace, ast_info_by_name, _seen | {target_name})
        if resolved is None:
            continue
        resolved, keep_kw = bind_call_site(resolved, call_site(ast_info, target_name))
        merge_concrete_params(merged, seen_names, resolved)
        if target_name in kw_targets and not keep_kw and not resolved_has_kind(resolved, VAR_KW):
            still_var_kw = False
        if target_name in pos_targets and not resolved_has_kind(resolved, VAR_POS):
            still_var_pos = False

    return still_var_kw, still_var_pos


def resolve_via_namespace(
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
    from .params import resolve_params

    kw_targets = ast_info.kwargs_forwarded_to if still_var_kw else []
    pos_targets = ast_info.args_forwarded_to if still_var_pos else []
    skip = ("cls", "self") + tuple(
        n for n in kw_targets + pos_targets if n.partition(".")[2] and n.partition(".")[0] == cls.__name__
    )

    still_var_kw, still_var_pos = resolve_targets(
        dedupe(kw_targets + pos_targets, skip=skip), kw_targets, pos_targets,
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

        resolved, keep_kw = bind_call_site(resolved, call_site(ast_info, target_name))
        merge_concrete_params(merged, seen_names, resolved)
        if target_name in method_kw_targets and not keep_kw and not resolved_has_kind(resolved, VAR_KW):
            still_var_kw = False
        if target_name in method_pos_targets and not resolved_has_kind(resolved, VAR_POS):
            still_var_pos = False

    return still_var_kw, still_var_pos
