"""``**kwargs`` / ``*args`` backtracing for methods and module-level functions.

:func:`resolve_params` resolves a method through ``cls(...)`` calls, the
class MRO and then module-level forwarding targets; :func:`resolve_function_params`
resolves a standalone function through its forwarding targets.  The two call
each other for mixed chains, with a ``_seen`` set guarding against cycles.
Call sites are honoured: arguments bound positionally or by keyword are
removed, and parameters reachable only through ``**kwargs`` become keyword-only.
"""
from __future__ import annotations

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
from ._targets import dedupe, resolve_targets, resolve_via_namespace
from .callables import function_info_of, signature_of
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
        still_var_kw, still_var_pos = resolve_via_namespace(
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

    still_var_kw, still_var_pos = resolve_targets(
        dedupe(kw_targets + pos_targets), kw_targets, pos_targets,
        ast_info, namespace, ast_info_by_name, _seen,
        merged, seen_names, has_var_kw, has_var_pos,
    )

    return finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)
