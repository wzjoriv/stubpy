"""Forwarding targets of ``**kwargs`` / ``*args``: module functions, classes and ``self.X`` / ``cls.X`` methods."""
from __future__ import annotations

import builtins
import inspect
import sys
from typing import Any

from stubpy._constants import FIELDS_PREFIX, VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo, NonLiteralDefault

from ._local_scope import local_target
from ._merge import (
    ParamWithHints,
    bind_call_site,
    call_site,
    has_kind,
    merge_concrete_params,
    resolved_has_kind,
)
from ._typed_kwargs import class_constructor, unpacked_kwargs
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


def _builtin(name: str, namespace: dict[str, Any]) -> Any:
    """The builtin *name* (``open``, ``print``) when the module does not rebind it."""
    return getattr(builtins, name, None) if namespace and name not in namespace and not name.startswith("_") else None


def _dotted(name: str, namespace: dict[str, Any], caller: FunctionInfo | None) -> tuple[Any, str | None, Any]:
    """Return ``(owner, method, object)`` for ``Cls.m`` / ``Cls().m`` / ``mod.sub.f``.

    *method* is set when the last part is looked up on a class; *object* is what the chain names.
    """
    parts = name.split(".")
    head = parts[0].removesuffix("()")
    obj = local_target(caller, head, namespace) or namespace.get(head, _builtin(head, namespace))
    for i, part in enumerate(parts[1:], start=1):
        if isinstance(obj, type) and i == len(parts) - 1:
            return obj, part, None
        obj = getattr(obj, part, None) if obj is not None else None
    return None, None, obj


def _target_params(
    target_name: str,
    namespace: dict[str, Any],
    ast_info_by_name: dict[str, FunctionInfo] | None,
    inner_seen: frozenset[str],
    caller: FunctionInfo | None = None,
) -> list[ParamWithHints] | None:
    """Return the resolved params of a namespace target, or ``None`` when it cannot be inspected.

    Targets defined in another module resolve their own forwarding in that module's namespace.
    """
    from .params import resolve_function_params, resolve_params

    if target_name.startswith(FIELDS_PREFIX):
        cls = _dotted(target_name[len(FIELDS_PREFIX):], namespace, caller)[2] if "." in target_name else \
            namespace.get(target_name[len(FIELDS_PREFIX):])
        return field_keywords(cls) if isinstance(cls, type) else None
    if "." in target_name:
        owner, method, target = _dotted(target_name, namespace, caller)
        if isinstance(owner, type) and method is not None:
            ns, infos = _home(owner, namespace, ast_info_by_name)
            return resolve_params(owner, method, namespace=ns, ast_info_by_name=infos, _seen=inner_seen)
        if target is None:
            return None
        target_name = target_name.rpartition(".")[2]
    else:
        target = local_target(caller, target_name, namespace) or namespace.get(target_name, _builtin(target_name, namespace))
    if target is None:
        return None
    ns, infos = _home(target, namespace, ast_info_by_name)
    if isinstance(target, type):
        special = class_constructor(target)
        if special is not None:
            return special
        return resolve_params(target, "__init__", namespace=ns, ast_info_by_name=infos, _seen=inner_seen)
    if not callable(target):
        return None
    target_sig = signature_of(target)
    if target_sig is None:
        return None
    target_params = list(target_sig.parameters.values())
    unpacked = unpacked_kwargs(target_params, get_hints_for_method(target))
    if unpacked is not None:
        return unpacked
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
        resolved = _target_params(target_name, namespace, ast_info_by_name, _seen | {target_name}, ast_info)
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


def field_keywords(cls: type) -> list[ParamWithHints] | None:
    """The fields a copy-with-changes of *cls* accepts: its ``__init__`` parameters as optional keywords."""
    sig = signature_of(cls)
    if sig is None:
        return None
    hints = get_hints_for_method(getattr(cls, "__init__", cls))
    return [(p.replace(kind=inspect.Parameter.KEYWORD_ONLY, default=NonLiteralDefault("...")), hints)
            for p in sig.parameters.values() if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
