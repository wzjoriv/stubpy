"""
Copy-with-changes idioms: ``dataclasses.replace(obj, **changes)`` and friends forward ``**changes`` to the fields.
"""
from __future__ import annotations

import ast

from stubpy._constants import FIELDS_PREFIX

_FUNCTIONS = {"dataclasses.replace", "copy.replace", "attrs.evolve", "attr.evolve"}
_BARE = {"replace", "evolve"}


def fields_target(call: ast.Call, fname: str, node: ast.FunctionDef | ast.AsyncFunctionDef,
                  copiers: set[str] | None = None) -> str | None:
    """``<fields>:Cls`` (or ``<fields>:self``) when *call* copies an instance of a known class with changes.

    A bare name counts only when it is in *copiers* (the module's imports of those functions); with *copiers*
    ``None`` the usual names ``replace`` / ``evolve`` are trusted.
    """
    bare = isinstance(call.func, ast.Name) and (fname in copiers if copiers is not None else fname in _BARE)
    if (fname in _FUNCTIONS or bare) and call.args:
        instance = call.args[0]
    elif fname.endswith("_replace") and isinstance(call.func, ast.Attribute):
        instance = call.func.value
    else:
        return None
    if not isinstance(instance, ast.Name):
        return None
    if instance.id == "self":
        return FIELDS_PREFIX + "self"
    params = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    arg = next((a for a in params if a.arg == instance.id), None)
    if arg is None or arg.annotation is None:
        return None
    ann = arg.annotation
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        text = ann.value
    else:
        text = ast.unparse(ann)
    return FIELDS_PREFIX + text if all(p.isidentifier() for p in text.split(".")) else None
