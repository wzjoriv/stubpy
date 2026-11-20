"""
Return types that are safe to infer from unannotated source: literals, ``self``, known calls, no return value.
"""
from __future__ import annotations

import ast

from stubpy._constants import SELF_RETURN
from stubpy.analysis._constants import RETURN_KEEPING_DECORATORS, STR_METHOD_RESULTS, TYPED_BUILTIN_CALLS

from ._literals import infer_type_from_literal
from ._nodes import decorator_name, is_stub_body
from ._returns import FunctionNode, own_nodes

_BOOL_COMPARE = (ast.Is, ast.IsNot, ast.In, ast.NotIn)


def _bound_names(node: FunctionNode, nodes: list[ast.AST]) -> set[str]:
    """Return the parameter names and every name the body binds."""
    args = node.args
    names = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    names.update(a.arg for a in (args.vararg, args.kwarg) if a is not None)
    for sub in nodes:
        if isinstance(sub, ast.Name) and not isinstance(sub.ctx, ast.Load):
            names.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(sub.name)
        elif isinstance(sub, ast.alias):
            names.add((sub.asname or sub.name).partition(".")[0])
    return names


def _terminates(body: list[ast.stmt]) -> bool:
    """True when control cannot fall off the end of *body*."""
    if not body:
        return False
    last = body[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    return isinstance(last, ast.If) and _terminates(last.body) and _terminates(last.orelse)


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str))


def _receiver(node: FunctionNode) -> str | None:
    """Return ``"self"`` or ``"cls"`` when the first parameter carries that conventional name."""
    args = node.args.posonlyargs + node.args.args
    return args[0].arg if args and args[0].arg in ("self", "cls") else None


def _call_type(call: ast.Call, receiver: str | None, shadowed: set[str]) -> tuple[str, str | None] | None:
    """Return ``(type, class_name_to_check)`` for a call whose result type is certain."""
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in shadowed and func.id != receiver:
            return None
        if func.id == receiver == "cls":
            return SELF_RETURN, None
        if func.id in TYPED_BUILTIN_CALLS:
            return TYPED_BUILTIN_CALLS[func.id], None
        return (func.id, func.id) if func.id[:1].isupper() else None
    if isinstance(func, ast.Call) and isinstance(func.func, ast.Name) and func.func.id == "type" \
            and "type" not in shadowed and len(func.args) == 1 and isinstance(func.args[0], ast.Name) \
            and func.args[0].id == receiver == "self":
        return SELF_RETURN, None
    if isinstance(func, ast.Attribute) and _is_str(func.value) and func.attr in STR_METHOD_RESULTS:
        return STR_METHOD_RESULTS[func.attr], None
    return None


def _expr_type(expr: ast.expr, receiver: str | None, shadowed: set[str]) -> tuple[str, str | None] | None:
    """Return ``(type, class_name_to_check)`` for a returned expression, or ``None`` when not certain."""
    if isinstance(expr, ast.JoinedStr):
        return "str", None
    if isinstance(expr, ast.Name) and expr.id == receiver == "self":
        return SELF_RETURN, None
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return "bool", None
    if isinstance(expr, ast.Compare) and all(isinstance(op, _BOOL_COMPARE) for op in expr.ops):
        return "bool", None
    if isinstance(expr, ast.Call):
        return _call_type(expr, receiver, shadowed)
    literal = infer_type_from_literal(expr)
    return (literal, None) if literal and literal != "Any" else None


def inferred_return(node: FunctionNode) -> tuple[str | None, str | None]:
    """Return the certain return type of an unannotated function and the local class it names, if any.

    ``None`` for a function without a ``return`` value (a stub body, a generator or a decorated
    function excepted); one literal type, ``str`` for f-strings and ``str`` methods of a string
    literal, ``int`` / ``bool`` / ``str`` for builtins such as ``len`` / ``isinstance`` / ``repr``,
    ``bool`` for ``not`` and identity or membership tests, ``Self`` for ``return self`` /
    ``cls(...)``, or ``Name`` for ``return Name(...)``, which the caller keeps only when ``Name``
    is a class of the module.  Anything else, or returns that disagree, give ``None``.
    """
    if node.returns is not None or is_stub_body(node.body):
        return None, None
    if any(decorator_name(d) not in RETURN_KEEPING_DECORATORS for d in node.decorator_list):
        return None, None
    nodes = own_nodes(node)
    if any(isinstance(sub, (ast.Yield, ast.YieldFrom)) for sub in nodes):
        return None, None
    returns = [sub for sub in nodes if isinstance(sub, ast.Return)]
    valued = [r for r in returns if r.value is not None]
    if not valued:
        ends_in_raise = isinstance(node.body[-1], ast.Raise)
        return (None, None) if ends_in_raise else ("None", None)
    if len(valued) != len(returns) or not _terminates(node.body):
        return None, None
    receiver = _receiver(node)
    shadowed = _bound_names(node, nodes)
    found = {_expr_type(r.value, receiver, shadowed) for r in valued if r.value is not None}
    only = found.pop() if len(found) == 1 else None
    return only if only is not None else (None, None)
