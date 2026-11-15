"""Harvest one class definition into a :class:`ClassInfo`."""
from __future__ import annotations

import ast

from stubpy.analysis.astutil import taken_branches

from ._functions import harvest_function_node
from ._hints import HintNames, split_hints
from ._literals import infer_type_from_literal
from ._nodes import type_params, unparse
from .models import ClassInfo, VariableInfo


def harvest_class(node: ast.ClassDef, hint_names: HintNames) -> ClassInfo:
    """Build a :class:`ClassInfo` from the methods, attributes and classes in the class body."""
    bases = [unparse(b) or "" for b in node.bases]
    bases += [f"{kw.arg}={unparse(kw.value)}" for kw in node.keywords if kw.arg]
    decorator_nodes, hints = split_hints(node.decorator_list, hint_names)
    info = ClassInfo(
        name=node.name,
        lineno=node.lineno,
        bases=[b for b in bases if b],
        decorators=[d for d in (unparse(d) for d in decorator_nodes) if d],
        hint_ignore=hints.ignore,
        type_params=type_params(node),
    )
    _harvest_body(node.body, info, hint_names)
    return info


def _harvest_body(body: list[ast.stmt], info: ClassInfo, hint_names: HintNames) -> None:
    """Add the definitions in a class *body* to *info*, following statically known ``if`` branches."""
    for child in body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.methods.append(harvest_function_node(child, hint_names))
        elif isinstance(child, ast.ClassDef):
            info.classes.append(harvest_class(child, hint_names))
        elif isinstance(child, ast.If):
            _harvest_body(taken_branches(child), info, hint_names)
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            info.attributes.append(VariableInfo(
                name=child.target.id,
                lineno=child.lineno,
                annotation_str=unparse(child.annotation),
                value_repr=unparse(child.value) if child.value else None,
            ))
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    info.attributes.append(VariableInfo(
                        name=target.id,
                        lineno=child.lineno,
                        value_repr=unparse(child.value),
                        inferred_type_str=infer_type_from_literal(child.value),
                    ))
