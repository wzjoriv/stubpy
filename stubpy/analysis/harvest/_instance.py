"""
Instance attributes a class assigns through ``self`` in its methods, and its ``__slots__``.
"""
from __future__ import annotations

import ast
from collections import deque

from ._literals import infer_type_from_literal
from ._nodes import children, unparse
from .models import VariableInfo

_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _assignments(fn: ast.FunctionDef | ast.AsyncFunctionDef, receiver: str):
    """Yield ``(name, annotation, value, lineno)`` for each ``self.x = ...`` / ``self.x: T = ...`` in *fn*'s scope."""
    stack: deque[ast.AST] = deque(fn.body)
    while stack:
        sub = stack.popleft()
        if isinstance(sub, _SCOPES):
            continue
        stack.extend(children(sub))
        if isinstance(sub, ast.AnnAssign):
            targets, annotation, value = [sub.target], sub.annotation, sub.value
        elif isinstance(sub, ast.Assign):
            targets, annotation, value = sub.targets, None, sub.value
        else:
            continue
        for target in targets:
            if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id == receiver):
                yield target.attr, annotation, value, sub.lineno


def _without_none(annotation: str) -> list[str]:
    """The members of the union *annotation* other than ``None`` (``Optional[X]`` counts as ``X | None``)."""
    try:
        node = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return [annotation]
    if isinstance(node, ast.Subscript) and (unparse(node.value) or "").rpartition(".")[2] == "Optional":
        node = node.slice
    members: list[ast.expr] = []
    stack = [node]
    while stack:
        part = stack.pop(0)
        if isinstance(part, ast.BinOp) and isinstance(part.op, ast.BitOr):
            stack = [part.left, part.right, *stack]
        else:
            members.append(part)
    return [m for m in (unparse(x) for x in members) if m and m != "None"]


def _or_type(value: ast.BoolOp, params: dict[str, str]) -> str | None:
    """The type of ``a or b``: the truthy part of *a* joined with the type of *b*."""
    if not isinstance(value.op, ast.Or):
        return None
    parts: list[str] = []
    for i, operand in enumerate(value.values):
        found = _value_type(operand, params)
        if found is None:
            return None
        parts.extend(_without_none(found) if i < len(value.values) - 1 else [found])
    return " | ".join(dict.fromkeys(parts))


def _value_type(value: ast.expr | None, params: dict[str, str]) -> str | None:
    """Infer a type from a literal, a ``Class(...)`` call or a parameter with an annotation."""
    if value is None:
        return None
    if isinstance(value, ast.Name) and value.id in params:
        return params[value.id]
    if isinstance(value, ast.BoolOp):
        return _or_type(value, params)
    if isinstance(value, ast.Call):
        func = unparse(value.func) or ""
        last = func.rpartition(".")[2]
        return func if last[:1].isupper() and func.replace(".", "").isidentifier() else None
    return infer_type_from_literal(value)


def instance_attributes(node: ast.ClassDef) -> list[VariableInfo]:
    """Return the attributes assigned through the receiver of the class's methods.

    An annotation wins; else the type comes from a literal, a constructor call or an annotated parameter
    (``__init__`` first), joined into a union.  When any assignment has an unknown type, the attribute
    is kept with ``annotation_str=None``.
    """
    methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    methods.sort(key=lambda m: m.name != "__init__")
    found: dict[str, tuple[int, str | None, set[str], bool]] = {}
    for fn in methods:
        args = fn.args.posonlyargs + fn.args.args
        if not args or any(unparse(d) in ("staticmethod", "classmethod") for d in fn.decorator_list):
            continue
        params = {a.arg: unparse(a.annotation) for a in fn.args.args + fn.args.kwonlyargs if a.annotation}
        for name, annotation, value, lineno in _assignments(fn, args[0].arg):
            line, ann, types, unknown = found.get(name, (lineno, None, set(), False))
            if annotation is not None and ann is None:
                ann = unparse(annotation)
            inferred = _value_type(value, params)
            if inferred is None:
                unknown = True
            else:
                types.add(inferred)
            found[name] = (min(line, lineno), ann, types, unknown)
    out: list[VariableInfo] = []
    for name, (line, ann, types, unknown) in found.items():
        typed = ann
        if typed is None and not unknown:
            rest = sorted(types - {"None"})
            typed = " | ".join(rest + (["None"] if "None" in types else [])) if rest else None
        out.append(VariableInfo(name=name, lineno=line, annotation_str=typed))
    return sorted(out, key=lambda v: v.lineno)


def slot_names(node: ast.ClassDef) -> list[str]:
    """Return the names a literal ``__slots__`` declares."""
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__slots__" for t in stmt.targets):
            value = stmt.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return [value.value]
            if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                return [e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []
