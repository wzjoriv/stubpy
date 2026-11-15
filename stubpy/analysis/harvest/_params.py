"""Parameter and return metadata extracted from a function definition node."""
from __future__ import annotations

import ast

from stubpy.analysis.astutil import iter_statements

from ._literals import infer_type_from_literal
from ._nodes import unparse
from .models import RawParam

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _positional_defaults(node: FunctionNode) -> list[tuple[ast.arg, ast.expr | None]]:
    """Pair each positional parameter with its default expression, if any."""
    positional = node.args.posonlyargs + node.args.args
    first_default = len(positional) - len(node.args.defaults)
    return [
        (arg, node.args.defaults[i - first_default] if i >= first_default else None)
        for i, arg in enumerate(positional)
    ]


def collect_annotations(node: FunctionNode) -> dict[str, str]:
    """Return unparsed annotations by parameter name; variadics keyed ``*name`` / ``**name``."""
    anns: dict[str, str] = {}
    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
        if arg.annotation:
            s = unparse(arg.annotation)
            if s:
                anns[arg.arg] = s

    if node.args.vararg and node.args.vararg.annotation:
        s = unparse(node.args.vararg.annotation)
        if s:
            anns[f"*{node.args.vararg.arg}"] = s

    if node.args.kwarg and node.args.kwarg.annotation:
        s = unparse(node.args.kwarg.annotation)
        if s:
            anns[f"**{node.args.kwarg.arg}"] = s
    return anns


def infer_default_types(node: FunctionNode, annotations: dict[str, str]) -> dict[str, str]:
    """Infer types for unannotated parameters from their literal defaults."""
    pairs = _positional_defaults(node)
    pairs += list(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True))
    inferred: dict[str, str] = {}
    for arg, default in pairs:
        if arg.arg in annotations or default is None:
            continue
        t = infer_type_from_literal(default)
        if t and t != "None":
            inferred[arg.arg] = t
    return inferred


def infer_return_type(node: FunctionNode) -> str | None:
    """Infer a return type from literal ``return`` statements (nested functions excluded); several become a union."""
    return_types: set[str] = set()
    for stmt in iter_statements(node, enter_functions=False):
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            t = infer_type_from_literal(stmt.value)
            if t:
                return_types.add(t)
    if len(return_types) == 1:
        return return_types.pop()
    if len(return_types) > 1:
        return " | ".join(sorted(return_types))
    return None


def build_raw_params(
    node: FunctionNode,
    annotations: dict[str, str],
    inferred: dict[str, str],
) -> list[RawParam]:
    """Return every parameter of *node* as a :class:`RawParam`, in declaration order."""
    params: list[RawParam] = []
    n_posonly = len(node.args.posonlyargs)
    for i, (arg, default) in enumerate(_positional_defaults(node)):
        params.append(RawParam(
            name=arg.arg,
            kind="POSITIONAL_ONLY" if i < n_posonly else "POSITIONAL_OR_KEYWORD",
            annotation_str=annotations.get(arg.arg),
            inferred_type_str=inferred.get(arg.arg),
            default_repr=unparse(default) if default is not None else None,
        ))
    if node.args.vararg:
        params.append(RawParam(
            name=node.args.vararg.arg,
            kind="VAR_POSITIONAL",
            annotation_str=annotations.get(f"*{node.args.vararg.arg}"),
        ))
    for arg, kw_def in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        params.append(RawParam(
            name=arg.arg,
            kind="KEYWORD_ONLY",
            annotation_str=annotations.get(arg.arg),
            inferred_type_str=inferred.get(arg.arg),
            default_repr=unparse(kw_def) if kw_def is not None else None,
        ))
    if node.args.kwarg:
        params.append(RawParam(
            name=node.args.kwarg.arg,
            kind="VAR_KEYWORD",
            annotation_str=annotations.get(f"**{node.args.kwarg.arg}"),
        ))
    return params
