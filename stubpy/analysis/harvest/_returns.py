"""
Return types that follow from a function's shape: generators and functions that always raise.
"""
from __future__ import annotations

import ast

from ._literals import infer_type_from_literal
from ._nodes import children, is_stub_body

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def own_nodes(node: FunctionNode) -> list[ast.AST]:
    """Return every node in *node*'s own scope (nested functions, lambdas and classes excluded)."""
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(node.body)
    while stack:
        sub = stack.pop()
        out.append(sub)
        if not isinstance(sub, _SCOPES):
            stack.extend(children(sub))
    return out


def _union(types: set[str]) -> str:
    return " | ".join(sorted(types, key=lambda t: (t == "None", t)))


def _yield_type(nodes: list[ast.AST]) -> str | None:
    """Return the union of the literal yield types, or ``None`` when one is not a literal."""
    types: set[str] = set()
    for sub in nodes:
        if isinstance(sub, ast.YieldFrom):
            return None
        if isinstance(sub, ast.Yield):
            found = "None" if sub.value is None else infer_type_from_literal(sub.value)
            if found is None:
                return None
            types.add(found)
    return _union(types) if types else None


def _always_raises(node: FunctionNode, nodes: list[ast.AST]) -> bool:
    """True when the body ends with a ``raise`` and never returns; ``raise NotImplementedError`` stubs excluded."""
    body = node.body
    if not body or is_stub_body(body) or not isinstance(body[-1], ast.Raise) or body[-1].exc is None:
        return False
    return not any(isinstance(sub, (ast.Return, ast.Yield, ast.YieldFrom, ast.Try, ast.With, ast.AsyncWith))
                   for sub in nodes)


def structural_return(node: FunctionNode) -> str | None:
    """Return ``Iterator[T]`` / ``Generator[T, S, R]`` / ``AsyncIterator[T]`` for literal generators, ``NoReturn``
    for functions that always raise, else ``None``.
    """
    nodes = own_nodes(node)
    if any(isinstance(sub, (ast.Yield, ast.YieldFrom)) for sub in nodes):
        yielded = _yield_type(nodes)
        if yielded is None:
            return None
        if isinstance(node, ast.AsyncFunctionDef):
            return f"AsyncIterator[{yielded}]"
        returns = [sub for sub in nodes if isinstance(sub, ast.Return) and sub.value is not None]
        sent = any(isinstance(sub, ast.Yield) and _is_value(sub, nodes) for sub in nodes)
        if not returns and not sent:
            return f"Iterator[{yielded}]"
        returned = {infer_type_from_literal(r.value) for r in returns} or {"None"}
        if None in returned:
            return None
        return f"Generator[{yielded}, {'Any' if sent else 'None'}, {_union(returned)}]"
    return "NoReturn" if _always_raises(node, nodes) else None


def _is_value(yield_node: ast.Yield, nodes: list[ast.AST]) -> bool:
    """True when the ``yield`` expression's result is used (the generator receives sent values)."""
    for sub in nodes:
        if isinstance(sub, ast.Expr) and sub.value is yield_node:
            return False
    return True
