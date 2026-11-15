"""``**kwargs`` / ``*args`` backtracing for methods and module-level functions.

:func:`resolve_params` resolves a method through ``cls(...)`` calls, the
class MRO and then module-level forwarding targets; :func:`resolve_function_params`
resolves a standalone function through its forwarding targets.  The two call
each other for mixed chains, with a ``_seen`` set guarding against cycles.
Call sites are honoured: arguments bound positionally or by keyword are
removed, and parameters reachable only through ``**kwargs`` become keyword-only.
"""
from __future__ import annotations

import sys
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

from ._cls_call import detect_cls_call
from ._merge import (
    CallSite,
    ParamWithHints,
    bind_call_site,
    call_site,
    concrete_own,
    consumed_params,
    finalise_variadics,
    has_kind,
    merge_concrete_params,
    resolved_has_kind,
)
from ._mro import walk_mro
from .callables import function_info_of, signature_of, unwrap_callable
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

    Strategies, in order: no variadics (own params unchanged); a
    ``cls(..., **kwargs)`` / ``type(self)(**kwargs)`` call resolves against
    ``cls.__init__``; the MRO walk; then module-level forwarding targets
    found in *namespace*.  ``self`` / ``cls`` are excluded from the result.
    Without *ast_info* the method's source is analysed, when available.

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

    raw = cls.__dict__.get(method_name)
    info = ast_info if ast_info is not None else function_info_of(raw)
    if _seen is None:
        _seen = frozenset({f"{cls.__name__}.{method_name}"})

    merged = concrete_own(own_params, own_hints)
    seen_names = {p.name for p, _ in merged}
    merged += consumed_params(info, seen_names)

    if has_var_kw and method_name != "__init__" and "__init__" not in _seen:
        found, explicit = detect_cls_call(cls, method_name, info)
        if found:
            init = resolve_params(
                cls, "__init__", namespace=namespace, ast_info_by_name=ast_info_by_name,
                _seen=_seen | {"__init__"},
            )
            site = call_site(info, "cls") if info is not None else CallSite(excluded=frozenset(explicit))
            resolved, keep_kw = bind_call_site(init, site)
            merge_concrete_params(merged, seen_names, resolved)
            still_kw = keep_kw or resolved_has_kind(resolved, VAR_KW)
            return finalise_variadics(merged, own_params, own_hints, has_var_pos, still_kw)

    still_var_kw, still_var_pos = walk_mro(
        cls, method_name, merged, seen_names, has_var_kw, has_var_pos,
    )

    if (still_var_kw or still_var_pos) and namespace and info is not None:
        still_var_kw, still_var_pos = _resolve_via_namespace(
            cls, info, namespace, ast_info_by_name, _seen,
            merged, seen_names, still_var_kw, still_var_pos,
        )

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

    Each forwarding target recorded in *ast_info* (or found in the
    function's source) is looked up in *namespace*; class targets resolve
    through their ``__init__`` and ``Cls().method`` targets through the
    method.  ``*args`` / residual ``**kwargs`` are kept when unresolved.
    """
    if live_fn is None:
        return []

    own_sig = signature_of(live_fn)
    if own_sig is None:
        return []
    own_params = list(own_sig.parameters.values())

    own_hints = get_hints_for_method(live_fn)
    has_var_kw = has_kind(own_params, VAR_KW)
    has_var_pos = has_kind(own_params, VAR_POS)
    if not has_var_kw and not has_var_pos:
        return [(p, own_hints) for p in own_params]

    if ast_info is None:
        ast_info = function_info_of(live_fn)
    if ast_info is None:
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
    merged += consumed_params(ast_info, seen_names)

    still_var_kw, still_var_pos = _resolve_targets(
        _dedupe(kw_targets + pos_targets), kw_targets, pos_targets,
        ast_info, namespace, ast_info_by_name, _seen,
        merged, seen_names, has_var_kw, has_var_pos,
    )

    return finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)


def _dedupe(names: list[str], skip: tuple[str, ...] = ()) -> list[str]:
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
    skip = ("cls", "self") + tuple(
        n for n in kw_targets + pos_targets if n.partition(".")[2] and n.partition(".")[0] == cls.__name__
    )

    still_var_kw, still_var_pos = _resolve_targets(
        _dedupe(kw_targets + pos_targets, skip=skip), kw_targets, pos_targets,
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
