"""Statement-level AST traversal, much cheaper than :func:`ast.walk` over every expression."""
from __future__ import annotations

import ast
from collections.abc import Iterator

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def iter_statements(node: ast.AST, *, enter_functions: bool = True) -> Iterator[ast.stmt]:
    """Yield every statement nested in *node*'s blocks, depth first, without visiting expressions.

    With ``enter_functions=False`` the bodies of nested functions and
    classes are skipped, but the definitions themselves are yielded.

    Examples
    --------
    >>> tree = ast.parse("if x:\\n    import a\\nelse:\\n    def f():\\n        import b")
    >>> [type(s).__name__ for s in iter_statements(tree)]
    ['If', 'Import', 'FunctionDef', 'Import']
    """
    for field in ("body", "orelse", "finalbody", "handlers", "cases"):
        for child in getattr(node, field, None) or ():
            if isinstance(child, ast.stmt):
                yield child
                if not enter_functions and isinstance(child, (*_FUNCTION_NODES, ast.ClassDef)):
                    continue
            yield from iter_statements(child, enter_functions=enter_functions)
