"""Detection of ``cls(..., **kwargs)`` calls inside classmethods."""
from __future__ import annotations

import ast

from stubpy.analysis.harvest.models import FunctionInfo

from .callables import source_tree_of


def scan_cls_call_inline(cls: type, method_name: str) -> tuple[bool, set[str]]:
    """Parse the method source for a ``cls(...)`` / ``cls.__init__(...)`` call taking ``**kwargs``.

    Returns ``(found, explicit_keyword_names)``.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return False, set()

    fn = raw.__func__ if isinstance(raw, classmethod) else raw
    tree = source_tree_of(fn)
    if tree is None:
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
    """Return ``(found, explicit_keyword_names)`` for a ``cls(..., **kwargs)`` call in a method.

    ``type(self)(**kwargs)`` counts as a ``cls`` call.  Uses *ast_info* when
    given, else parses the method source.
    """
    if ast_info is not None:
        if "cls" in ast_info.kwargs_forwarded_to:
            return True, set(ast_info.kwargs_explicit_names.get("cls", ()))
        return False, set()
    return scan_cls_call_inline(cls, method_name)
