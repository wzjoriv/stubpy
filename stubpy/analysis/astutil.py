"""Statement-level AST traversal, much cheaper than :func:`ast.walk` over every expression."""
from __future__ import annotations

import ast
import operator
import sys
from collections.abc import Iterator

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

_COMPARE_OPS = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


def _dotted(node: ast.expr) -> str | None:
    """Return ``a.b.c`` for a name or attribute chain, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _static_value(node: ast.expr) -> object:
    """Return the value of ``sys.version_info`` (sliced or indexed), ``sys.platform`` or a literal; ``...`` when unknown."""
    if isinstance(node, ast.Subscript) and _dotted(node.value) == "sys.version_info":
        try:
            index = ast.literal_eval(node.slice) if not isinstance(node.slice, ast.Slice) else slice(
                *(ast.literal_eval(p) if p is not None else None for p in (node.slice.lower, node.slice.upper, node.slice.step))
            )
            return tuple(sys.version_info)[index]
        except Exception:
            return ...
    dotted = _dotted(node)
    if dotted == "sys.version_info":
        return tuple(sys.version_info)
    if dotted == "sys.platform":
        return sys.platform
    try:
        return ast.literal_eval(node)
    except Exception:
        return ...


def static_truth(test: ast.expr) -> bool | None:
    """Return the value of an ``if`` test a type checker evaluates statically, or ``None``.

    Understands ``TYPE_CHECKING`` (always true), comparisons of
    ``sys.version_info`` and ``sys.platform`` (against the running
    interpreter), ``not``, ``and`` and ``or``.

    Examples
    --------
    >>> static_truth(ast.parse("TYPE_CHECKING", mode="eval").body)
    True
    >>> static_truth(ast.parse("sys.version_info < (3, 0)", mode="eval").body)
    False
    >>> static_truth(ast.parse("DEBUG", mode="eval").body) is None
    True
    """
    if isinstance(test, (ast.Name, ast.Attribute)) and (_dotted(test) or "").rpartition(".")[2] == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = static_truth(test.operand)
        return None if inner is None else not inner
    if isinstance(test, ast.BoolOp):
        values = [static_truth(v) for v in test.values]
        if isinstance(test.op, ast.And):
            return False if False in values else (None if None in values else True)
        return True if True in values else (None if None in values else False)
    if _is_platform_startswith(test):
        return sys.platform.startswith(test.args[0].value)  # type: ignore[attr-defined]
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and type(test.ops[0]) in _COMPARE_OPS:
        left, right = _static_value(test.left), _static_value(test.comparators[0])
        if left is ... or right is ... or not (_is_sys(test.left) or _is_sys(test.comparators[0])):
            return None
        try:
            return bool(_COMPARE_OPS[type(test.ops[0])](left, right))
        except TypeError:
            return None
    return None


def _is_sys(node: ast.expr) -> bool:
    target = node.value if isinstance(node, ast.Subscript) else node
    return (_dotted(target) or "") in ("sys.version_info", "sys.platform")


def _is_platform_startswith(test: ast.expr) -> bool:
    """True for ``sys.platform.startswith("...")``."""
    return (
        isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) and test.func.attr == "startswith"
        and _dotted(test.func.value) == "sys.platform" and len(test.args) == 1 and not test.keywords
        and isinstance(test.args[0], ast.Constant) and isinstance(test.args[0].value, str)
    )


def is_version_test(test: ast.expr) -> bool:
    """Return ``True`` for a test built only from ``sys.version_info`` / ``sys.platform`` checks.

    Accepted: ``sys.version_info`` (or a slice / index of it) compared with
    a literal, ``sys.platform`` compared for (in)equality or
    ``sys.platform.startswith(...)``, combined with ``and``, ``or`` and ``not``.

    Examples
    --------
    >>> is_version_test(ast.parse("sys.version_info[:2] >= (3, 12) and sys.platform == 'win32'", mode="eval").body)
    True
    >>> is_version_test(ast.parse("TYPE_CHECKING", mode="eval").body)
    False
    """
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return is_version_test(test.operand)
    if isinstance(test, ast.BoolOp):
        return all(is_version_test(v) for v in test.values)
    if _is_platform_startswith(test):
        return True
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and type(test.ops[0]) in _COMPARE_OPS):
        return False
    left, right = test.left, test.comparators[0]
    sys_side, other = (left, right) if _is_sys(left) else (right, left)
    if not _is_sys(sys_side) or _is_sys(other) or _static_value(other) is ...:
        return False
    target = sys_side.value if isinstance(sys_side, ast.Subscript) else sys_side
    if _dotted(target) == "sys.platform":
        return isinstance(test.ops[0], (ast.Eq, ast.NotEq)) and sys_side is target
    return True


def version_chain(node: ast.If) -> list[tuple[ast.expr | None, list[ast.stmt]]]:
    """Return ``(test, body)`` per branch of an ``if`` / ``elif`` / ``else`` chain of version tests; ``None`` tests ``else``.

    An ``elif`` whose test is not a version test ends the chain: it lands,
    as a nested ``if``, in the ``else`` branch.
    """
    branches: list[tuple[ast.expr | None, list[ast.stmt]]] = []
    current = node
    while True:
        branches.append((current.test, current.body))
        orelse = current.orelse
        if len(orelse) == 1 and isinstance(orelse[0], ast.If) and is_version_test(orelse[0].test):
            current = orelse[0]
            continue
        if orelse:
            branches.append((None, orelse))
        return branches


def taken_index(tests: list[ast.expr | None]) -> int | None:
    """Return the index of the branch this interpreter takes, ``None`` when it takes none."""
    for i, test in enumerate(tests):
        if test is None or static_truth(test):
            return i
    return None


def taken_branches(node: ast.If) -> list[ast.stmt]:
    """Return the statements of the branch(es) of *node* a type checker would consider."""
    truth = static_truth(node.test)
    if truth is None:
        return node.body + node.orelse
    return node.body if truth else node.orelse


def iter_statements(node: ast.AST, *, enter_functions: bool = True) -> Iterator[ast.stmt]:
    """Yield every statement nested in *node*'s blocks, depth first, without visiting expressions.

    With ``enter_functions=False`` the bodies of nested functions and
    classes are skipped, but the definitions themselves are yielded.  An
    ``if`` whose test is statically known (see :func:`static_truth`) only
    contributes its taken branch.

    Examples
    --------
    >>> tree = ast.parse("if x:\\n    import a\\nelse:\\n    def f():\\n        import b")
    >>> [type(s).__name__ for s in iter_statements(tree)]
    ['If', 'Import', 'FunctionDef', 'Import']
    """
    if isinstance(node, ast.If):
        children: list = taken_branches(node)
    else:
        children = [c for f in ("body", "orelse", "finalbody", "handlers", "cases") for c in getattr(node, f, None) or ()]
    for child in children:
        if isinstance(child, ast.stmt):
            yield child
            if not enter_functions and isinstance(child, (*_FUNCTION_NODES, ast.ClassDef)):
                continue
        yield from iter_statements(child, enter_functions=enter_functions)
