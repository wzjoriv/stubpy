"""
Branch dispatch: ``**kwargs`` / ``*args`` forwarded to a different callee per literal value of one parameter.
"""
from __future__ import annotations

import ast

from ._calls import call_func_name, iter_body_calls
from .models import BranchDispatch

_Case = tuple[tuple[str, ...], tuple[str, ...], bool]


def scan_dispatch(node: ast.FunctionDef | ast.AsyncFunctionDef) -> BranchDispatch | None:
    """Return the literal dispatch of *node*'s variadics, from ``if`` / ``match`` statements or a dict lookup."""
    kwargs_name = node.args.kwarg.arg if node.args.kwarg else None
    varargs_name = node.args.vararg.arg if node.args.vararg else None
    if not (kwargs_name or varargs_name):
        return None
    names = (kwargs_name, varargs_name)
    params = {a.arg for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    return _statement_dispatch(node.body, params, names) or _dict_dispatch(node, params, names)


def _is_literal(node: ast.expr, params: set[str]) -> bool:
    """A constant or an ``Enum.MEMBER``-style dotted name not rooted at a parameter."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int, bytes, bool)) or node.value is None
    while isinstance(node, ast.Attribute):
        node = node.value
        if isinstance(node, ast.Name):
            return node.id not in params
    return False


def _literal_test(test: ast.expr, params: set[str]) -> tuple[str, tuple[str, ...]] | None:
    """``(selector, literals)`` for ``p == lit``, ``lit == p``, ``p is lit``, ``p in (lits)`` and ``or`` of those."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        parts = [_literal_test(v, params) for v in test.values]
        if any(p is None for p in parts) or len({p[0] for p in parts}) != 1:
            return None
        return parts[0][0], tuple(lit for p in parts for lit in p[1])
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return None
    left, op, right = test.left, test.ops[0], test.comparators[0]
    if isinstance(op, (ast.Eq, ast.Is)):
        if isinstance(right, ast.Name) and right.id in params:
            left, right = right, left
        if isinstance(left, ast.Name) and left.id in params and _is_literal(right, params):
            return left.id, (ast.unparse(right),)
    elif isinstance(op, ast.In) and isinstance(left, ast.Name) and left.id in params:
        if isinstance(right, (ast.Tuple, ast.List, ast.Set)) and right.elts and all(
                _is_literal(e, params) for e in right.elts):
            return left.id, tuple(ast.unparse(e) for e in right.elts)
    return None


def _forwards(call: ast.Call, names: tuple[str | None, str | None]) -> tuple[bool, bool]:
    """Whether *call* passes on ``**kwargs`` and ``*args`` by name."""
    kwargs_name, varargs_name = names
    kw = kwargs_name is not None and any(
        k.arg is None and isinstance(k.value, ast.Name) and k.value.id == kwargs_name for k in call.keywords)
    pos = varargs_name is not None and any(
        isinstance(a, ast.Starred) and isinstance(a.value, ast.Name) and a.value.id == varargs_name
        for a in call.args)
    return kw, pos


def _callees(body: list[ast.stmt], names: tuple[str | None, str | None]) -> tuple[tuple[str, ...], bool]:
    """The named callees *body* forwards the variadics to, and whether it returns a lone forwarding call."""
    shell = ast.FunctionDef(name="_", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[],
                                                          defaults=[]), body=body, decorator_list=[])
    found: list[str] = []
    for call in iter_body_calls(shell):
        if any(_forwards(call, names)):
            name = call_func_name(call)
            if not name:
                return (), False
            if name not in found:
                found.append(name)
    returned = len(found) == 1 and any(
        isinstance(s, ast.Return) and isinstance(s.value, ast.Call) and call_func_name(s.value) == found[0]
        for s in body)
    return tuple(found), returned


def _terminates(body: list[ast.stmt]) -> bool:
    """True when *body* ends in ``return`` or ``raise``."""
    return bool(body) and isinstance(body[-1], (ast.Return, ast.Raise))


def _if_chain(stmt: ast.If, params: set[str], names: tuple, selector: str | None,
              ) -> tuple[str, list[_Case], set[str], bool] | None:
    """Walk an ``if`` / ``elif`` / ``else`` chain on one selector: ``(selector, cases, else callees, all return)``."""
    cases: list[_Case] = []
    rest: set[str] = set()
    final = True
    cur: ast.If | None = stmt
    while cur is not None:
        test = _literal_test(cur.test, params)
        if test is None or (selector is not None and test[0] != selector):
            return None
        selector = test[0]
        callees, returned = _callees(cur.body, names)
        final = final and _terminates(cur.body)
        if callees:
            cases.append((test[1], callees, returned))
        if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
            cur = cur.orelse[0]
            continue
        rest |= set(_callees(cur.orelse, names)[0])
        cur = None
    return selector, cases, rest, final


def _pattern_literals(pattern: ast.AST, params: set[str]) -> tuple[str, ...] | None:
    """The literal sources a ``case`` pattern matches; ``None`` for any other pattern."""
    if isinstance(pattern, ast.MatchValue) and _is_literal(pattern.value, params):
        return (ast.unparse(pattern.value),)
    if isinstance(pattern, ast.MatchSingleton):
        return (repr(pattern.value),)
    if isinstance(pattern, ast.MatchOr):
        parts = [_pattern_literals(p, params) for p in pattern.patterns]
        return None if any(p is None for p in parts) else tuple(lit for p in parts for lit in p)
    return None


def _match(stmt: ast.Match, params: set[str], names: tuple) -> tuple[str, list[_Case], set[str]] | None:
    """``(selector, cases, wildcard callees)`` of ``match selector:`` with literal ``case`` patterns."""
    if not (isinstance(stmt.subject, ast.Name) and stmt.subject.id in params):
        return None
    cases: list[_Case] = []
    rest: set[str] = set()
    for case in stmt.cases:
        callees, returned = _callees(case.body, names)
        literals = _pattern_literals(case.pattern, params) if case.guard is None else None
        if literals is None:
            rest |= set(callees)
        elif callees:
            cases.append((literals, callees, returned))
    return stmt.subject.id, cases, rest


def _statement_dispatch(body: list[ast.stmt], params: set[str], names: tuple) -> BranchDispatch | None:
    """A dispatch from the top-level ``if`` chains or ``match`` of a function body."""
    selector: str | None = None
    kind = ""
    cases: list[_Case] = []
    rest: set[str] = set()
    closed = False
    for stmt in body:
        if closed:
            rest |= set(_callees([stmt], names)[0])
            continue
        if isinstance(stmt, ast.If) and kind != "match":
            chain = _if_chain(stmt, params, names, selector)
            if chain is not None:
                selector, found, other, closed = chain
                kind = "if"
                cases += found
                rest |= other
                continue
        elif isinstance(stmt, ast.Match) and not kind:
            found_match = _match(stmt, params, names)
            if found_match is not None:
                selector, cases, rest = found_match
                kind = "match"
                closed = True
                continue
    if selector is None or len(cases) < (1 if rest else 2):
        return None
    callees = rest | {c for _, cs, _ in cases for c in cs}
    return BranchDispatch(selector, kind, tuple(cases), frozenset(callees))


def _dict_dispatch(node: ast.FunctionDef | ast.AsyncFunctionDef, params: set[str], names: tuple,
                   ) -> BranchDispatch | None:
    """``{lit: Callee, ...}[selector](**kwargs)`` or ``TABLE[selector](**kwargs)`` for a module-level ``TABLE``."""
    for call in iter_body_calls(node):
        func = call.func
        if not (isinstance(func, ast.Subscript) and isinstance(func.slice, ast.Name) and func.slice.id in params):
            continue
        kw, pos = _forwards(call, names)
        if not (kw or pos):
            continue
        returned = any(isinstance(s, ast.Return) and s.value is call for s in ast.walk(node))
        table: str | None = None
        cases: list[_Case] = []
        if isinstance(func.value, ast.Name):
            table = func.value.id
        elif isinstance(func.value, ast.Dict) and all(
                k is not None and _is_literal(k, params) and isinstance(v, (ast.Name, ast.Attribute))
                for k, v in zip(func.value.keys, func.value.values, strict=True)):
            cases = [((ast.unparse(k),), (ast.unparse(v),), returned)
                     for k, v in zip(func.value.keys, func.value.values, strict=True)]
        else:
            return None
        return BranchDispatch(
            func.slice.id, "dict", tuple(cases), frozenset(c for _, cs, _ in cases for c in cs), table,
            kw, pos, sum(1 for a in call.args if not isinstance(a, ast.Starred)),
            frozenset(k.arg for k in call.keywords if k.arg is not None), returned,
        )
    return None
