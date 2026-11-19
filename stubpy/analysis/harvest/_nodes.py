"""
Small AST node helpers shared by the harvester.
"""
from __future__ import annotations

import ast
import importlib.util

from stubpy._constants import KNOWN_TYPE_NAMES

from ._calls import call_func_name

_TYPEVAR_CALL_NAMES: frozenset[str] = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple", "NewType"})


def unparse(node: ast.expr | None) -> str | None:
    """Unparse *node* to source text, or return ``None``."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def type_params(node: ast.AST) -> list[str]:
    """Return the PEP 695 type parameters of a ``def`` / ``class`` / ``type`` node as source text."""
    return [t for t in (unparse(p) for p in getattr(node, "type_params", None) or ()) if t]


def decorator_name(node: ast.expr) -> str:
    """Return the simple name of ``@name`` / ``@mod.name`` / ``@name(...)`` decorators, else ``""``."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def is_stub_body(body: list[ast.stmt]) -> bool:
    """Return ``True`` when *body* only holds a docstring, ``pass``, ``...`` or ``raise NotImplementedError``."""
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        return False
    return True


def is_main_guard(test: ast.expr) -> bool:
    """Return ``True`` for the test of ``if __name__ == "__main__":``."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def is_implicit_alias(node: ast.expr | None) -> bool:
    """Return ``True`` for an unannotated RHS that is unambiguously a type.

    That is a PEP 604 union, any subscript, or a known builtin/typing name.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.Name) and node.id in KNOWN_TYPE_NAMES:
        return True
    return False


def typevar_call_kind(node: ast.expr | None) -> str | None:
    """Return ``"TypeVar"`` / ``"ParamSpec"`` / ... when *node* calls one, else ``None``."""
    if not isinstance(node, ast.Call):
        return None
    name = call_func_name(node)
    return name if name in _TYPEVAR_CALL_NAMES else None


def findable(stmt: ast.Import | ast.ImportFrom) -> bool:
    """Return ``True`` when the top-level package of the import can be found (relative imports always can)."""
    if isinstance(stmt, ast.ImportFrom) and stmt.level:
        return True
    names = [stmt.module or ""] if isinstance(stmt, ast.ImportFrom) else [a.name for a in stmt.names]
    try:
        return all(importlib.util.find_spec(n.split(".")[0]) is not None for n in names if n)
    except (ImportError, ValueError):
        return False


def catches_import_error(handler: ast.ExceptHandler) -> bool:
    """Return ``True`` for ``except ImportError`` / ``ModuleNotFoundError`` (alone or in a tuple)."""
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(k, ast.Name) and k.id in ("ImportError", "ModuleNotFoundError") for k in kinds)
