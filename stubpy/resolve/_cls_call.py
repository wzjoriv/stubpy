"""Detection of ``cls(..., **kwargs)`` calls inside classmethods."""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

from ._merge import ParamWithHints, concrete_own, normalise_kind


def scan_cls_call_inline(cls: type, method_name: str) -> tuple[bool, set[str]]:
    """Parse the method source for a ``cls(...)`` / ``cls.__init__(...)`` call taking ``**kwargs``.

    Returns ``(found, explicit_keyword_names)``.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return False, set()

    fn = raw.__func__ if isinstance(raw, classmethod) else raw

    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except Exception:
        return False, set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_cls_call = (
            (isinstance(func, ast.Name) and func.id == "cls")
            or (
                isinstance(func, ast.Attribute)
                and func.attr == "__init__"
                and isinstance(func.value, ast.Name)
                and func.value.id == "cls"
            )
        )
        if not is_cls_call:
            continue
        if any(kw.arg is None for kw in node.keywords):
            explicit = {kw.arg for kw in node.keywords if kw.arg is not None}
            return True, explicit

    return False, set()


def detect_cls_call(
    cls: type,
    method_name: str,
    ast_info: FunctionInfo | None = None,
) -> tuple[bool, set[str]]:
    """Return ``(found, explicit_keyword_names)`` for a ``cls(..., **kwargs)`` call in a classmethod.

    Uses the pre-scanned *ast_info* when given, re-parsing the source only to
    recover the explicit keyword names.
    """
    if ast_info is not None:
        if "cls" in ast_info.kwargs_forwarded_to:
            _, explicit = scan_cls_call_inline(cls, method_name)
            return True, explicit
        return False, set()
    return scan_cls_call_inline(cls, method_name)


def merge_with_init(
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    explicit_kw: set[str],
    init_params: list[ParamWithHints],
) -> list[ParamWithHints]:
    """Merge a classmethod's own params with ``__init__``'s, skipping explicitly passed names."""
    merged = concrete_own(own_params, own_hints)
    seen = {p.name for p, _ in merged} | explicit_kw

    for p, h in init_params:
        if p.kind in (VAR_POS, VAR_KW):
            continue
        if p.name in seen:
            continue
        merged.append((normalise_kind(p), h))
        seen.add(p.name)

    if any(p.kind == VAR_KW for p, _ in init_params):
        kw_param = next((p for p in own_params if p.kind == VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged
