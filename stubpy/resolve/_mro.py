"""
The MRO walk: absorb ancestor parameters into a method's variadics.
"""
from __future__ import annotations

import dataclasses

from stubpy._constants import VAR_KW, VAR_POS

from ._cached_facts import function_info_of
from ._merge import ParamWithHints, bind_call_site, call_site, merge_concrete_params, resolved_has_kind
from .hints import get_raw_params


def _super_target(caller: object, method_name: str, parent: type) -> str | None:
    """Return the forwarding-target name the caller uses for *parent*'s method, or ``None`` if it has none.

    ``super().m(**kw)`` is recorded as ``m`` and ``Parent.m(self, **kw)`` as
    ``Parent.m``.  Returns *method_name* when the caller's source is unknown
    or a stub-like body (``...``), which is taken to forward to its parent.
    """
    info = function_info_of(caller)
    if info is None or info.is_stub_body:
        return method_name
    targets = info.kwargs_forwarded_to + info.args_forwarded_to
    for name in (f"{parent.__name__}.{method_name}", method_name):
        if name in targets:
            return name
    return None


def _names_later_parent(caller: object, method_name: str, cls: type, parent: type) -> bool:
    """Return ``True`` when the caller explicitly calls ``Later.method`` for a class after *parent* in the MRO."""
    info = function_info_of(caller)
    if info is None:
        return False
    mro = cls.__mro__
    later = mro[mro.index(parent) + 1:]
    targets = set(info.kwargs_forwarded_to + info.args_forwarded_to)
    return any(f"{k.__name__}.{method_name}" in targets for k in later)


def walk_mro(
    cls: type,
    method_name: str,
    merged: list[ParamWithHints],
    seen_names: set[str],
    still_var_kw: bool,
    still_var_pos: bool,
) -> tuple[bool, bool]:
    """Merge params from ancestors defining *method_name* until both variadics are resolved.

    Each level's call site (``super().m(a, b, **kw)``) binds its arguments
    before the next ancestor's params are absorbed; a level that does not
    forward its variadics stops the walk.  *merged* and *seen_names* are
    updated in place; returns the updated ``(still_var_kw, still_var_pos)``.
    """
    caller = cls.__dict__.get(method_name)
    args_open = still_var_pos
    for parent in cls.__mro__[1:]:
        if parent is object:
            break
        if method_name not in parent.__dict__:
            continue

        parent_params, parent_hints = get_raw_params(parent, method_name)
        if parent_params is None:
            continue

        target = _super_target(caller, method_name, parent)
        if target is None:
            if _names_later_parent(caller, method_name, cls, parent):
                continue
            break
        site = call_site(function_info_of(caller), target, forwards_args=args_open)
        site = dataclasses.replace(site, forwards_args=site.forwards_args and args_open)
        resolved, keep_kw = bind_call_site([(p, parent_hints) for p in parent_params], site)
        args_open = site.forwards_args and resolved_has_kind(resolved, VAR_POS)
        merge_concrete_params(merged, seen_names, resolved)

        still_var_kw = still_var_kw and (keep_kw or resolved_has_kind(resolved, VAR_KW))
        if site.forwards_args:
            still_var_pos = resolved_has_kind(resolved, VAR_POS)

        if not still_var_kw and not (still_var_pos and site.forwards_args):
            break
        caller = parent.__dict__[method_name]

    return still_var_kw, still_var_pos
