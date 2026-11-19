"""
Names bound by import statements inside a function body.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator

from .models import LocalImport

_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _own_imports(node: ast.AST) -> Iterator[ast.Import | ast.ImportFrom]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPES):
            continue
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child
        else:
            yield from _own_imports(child)


def scan_local_imports(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, LocalImport]:
    """Map each name bound by an import in *fn_node*'s own scope to what it imports."""
    found: dict[str, LocalImport] = {}
    for stmt in _own_imports(fn_node):
        for alias in stmt.names:
            if isinstance(stmt, ast.ImportFrom):
                if alias.name != "*":
                    found[alias.asname or alias.name] = LocalImport(stmt.level, stmt.module or "", alias.name)
            elif alias.asname:
                found[alias.asname] = LocalImport(0, alias.name, None)
            else:
                root = alias.name.partition(".")[0]
                found[root] = LocalImport(0, root, None)
    return found
