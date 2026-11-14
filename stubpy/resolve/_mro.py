"""The MRO walk: absorb ancestor parameters into a method's variadics."""
from __future__ import annotations

from stubpy._constants import VAR_KW, VAR_POS

from ._merge import ParamWithHints, has_kind, merge_concrete_params
from .hints import get_raw_params


def walk_mro(
    cls: type,
    method_name: str,
    merged: list[ParamWithHints],
    seen_names: set[str],
    still_var_kw: bool,
    still_var_pos: bool,
) -> tuple[bool, bool]:
    """Merge params from ancestors defining *method_name* until both variadics are resolved.

    *merged* and *seen_names* are updated in place; returns the updated
    ``(still_var_kw, still_var_pos)`` flags.
    """
    for parent in cls.__mro__[1:]:
        if parent is object:
            break
        if method_name not in parent.__dict__:
            continue

        parent_params, parent_hints = get_raw_params(parent, method_name)
        if parent_params is None:
            continue

        merge_concrete_params(merged, seen_names, [(p, parent_hints) for p in parent_params])

        if not has_kind(parent_params, VAR_KW):
            still_var_kw = False
        if not has_kind(parent_params, VAR_POS):
            still_var_pos = False

        if not still_var_kw and not still_var_pos:
            break

    return still_var_kw, still_var_pos
