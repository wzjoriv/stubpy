"""Type inference from literal AST expressions."""
from __future__ import annotations

import ast


def infer_type_from_literal(node: ast.expr) -> str | None:
    """Infer a type name from a literal AST expression, or return ``None``.

    Handles scalar constants, negated numbers, complex sums, and homogeneous
    ``list`` / ``tuple`` / ``set`` / ``dict`` displays.  ``...`` maps to ``Any``.

    Examples
    --------
    >>> import ast
    >>> infer_type_from_literal(ast.parse("42", mode="eval").body)
    'int'
    >>> infer_type_from_literal(ast.parse("[1, 2]", mode="eval").body)
    'list[int]'
    """
    if isinstance(node, ast.Constant):
        v = node.value
        for kind in (bool, int, float, str, bytes, complex):
            if isinstance(v, kind):
                return kind.__name__
        if v is None:
            return "None"
        if v is ...:
            return "Any"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = infer_type_from_literal(node.operand)
        if inner in ("int", "float"):
            return inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left = infer_type_from_literal(node.left)
        right = infer_type_from_literal(node.right)
        if "complex" in (left, right) and all(
            t in ("int", "float", "complex") for t in (left, right) if t
        ):
            return "complex"
    if isinstance(node, ast.List):
        if not node.elts:
            return "list"
        elem_types = {infer_type_from_literal(e) for e in node.elts}
        if len(elem_types) == 1 and None not in elem_types:
            return f"list[{elem_types.pop()}]"
        return "list"
    if isinstance(node, ast.Tuple):
        if not node.elts:
            return "tuple[()]"
        types = [infer_type_from_literal(e) for e in node.elts]
        if all(t is not None for t in types):
            return f"tuple[{', '.join(types)}]"
        return "tuple"
    if isinstance(node, ast.Set):
        if not node.elts:
            return "set"
        elem_types = {infer_type_from_literal(e) for e in node.elts}
        if len(elem_types) == 1 and None not in elem_types:
            return f"set[{elem_types.pop()}]"
        return "set"
    if isinstance(node, ast.Dict):
        if not node.keys:
            return "dict"
        key_types = {infer_type_from_literal(k) for k in node.keys if k is not None}
        val_types = {infer_type_from_literal(v) for v in node.values}
        if (len(key_types) == 1 and len(val_types) == 1
                and None not in key_types and None not in val_types):
            return f"dict[{key_types.pop()}, {val_types.pop()}]"
        return "dict"
    return None
