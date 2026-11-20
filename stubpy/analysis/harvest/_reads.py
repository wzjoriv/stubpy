"""
Read-only access to the variadics: ``kwargs["k"]``, ``kwargs.get("k", d)`` and ``args[i]``.
"""
from __future__ import annotations

import ast


def _const(node: ast.AST, kind: type) -> object | None:
    """The value of a constant of *kind*, else ``None``."""
    return node.value if isinstance(node, ast.Constant) and type(node.value) is kind else None


def _named(node: ast.AST, name: str | None) -> bool:
    """True when *node* is the bare name *name*."""
    return name is not None and isinstance(node, ast.Name) and node.id == name


def scan_reads(node: ast.FunctionDef | ast.AsyncFunctionDef, skip: set[str]) -> tuple[dict[str, str | None], int]:
    """Return the ``**kwargs`` keys read (with their default source, ``None`` when required) and the ``*args`` count read.

    Keys in *skip* (popped, deleted or assigned) are left out; a key also tested
    with ``"k" in kwargs`` gets the default ``...``.  An annotated ``*args`` and a
    ``**kwargs: Unpack[...]`` already say what they hold, so their reads are ignored.
    """
    kwarg, vararg = node.args.kwarg, node.args.vararg
    kwargs_name = kwarg.arg if kwarg and "Unpack" not in ast.unparse(kwarg.annotation or ast.Constant("")) else None
    varargs_name = vararg.arg if vararg and vararg.annotation is None else None
    keys: dict[str, str | None] = {}
    tested: set[str] = set()
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript) and isinstance(sub.ctx, ast.Load):
            if _named(sub.value, kwargs_name):
                key = _const(sub.slice, str)
                if key is not None:
                    keys.setdefault(key, None)
            elif _named(sub.value, varargs_name):
                index = _const(sub.slice, int)
                if isinstance(index, int) and index >= 0:
                    count = max(count, index + 1)
        elif (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get"
              and _named(sub.func.value, kwargs_name) and sub.args):
            key = _const(sub.args[0], str)
            if key is not None:
                keys[key] = ast.unparse(sub.args[1]) if len(sub.args) > 1 else "None"
        elif (isinstance(sub, ast.Compare) and len(sub.ops) == 1 and isinstance(sub.ops[0], (ast.In, ast.NotIn))
              and _named(sub.comparators[0], kwargs_name)):
            key = _const(sub.left, str)
            if key is not None:
                tested.add(key)
    for key in tested & keys.keys():
        if keys[key] is None:
            keys[key] = "..."
    return {k: v for k, v in keys.items() if k not in skip and k.isidentifier()}, count
