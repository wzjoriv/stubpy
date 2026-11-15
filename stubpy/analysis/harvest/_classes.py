"""Harvest one class definition into a :class:`ClassInfo`."""
from __future__ import annotations

import ast

from stubpy.analysis.astutil import is_version_test, taken_branches, taken_index, version_chain

from ._functions import harvest_function_node
from ._hints import HintNames, split_hints
from ._literals import infer_type_from_literal
from ._nodes import type_params, unparse
from .models import ClassInfo, VariableInfo, VersionBlock


def harvest_class(node: ast.ClassDef, hint_names: HintNames, version_branches: bool = False) -> ClassInfo:
    """Build a :class:`ClassInfo` from the methods, attributes and classes in the class body.

    With *version_branches*, every branch of a version ``if`` is harvested
    and its members tagged with their ``branch``; otherwise only the taken one.
    """
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
    _harvest_body(node.body, info, hint_names, version_branches)
    return info


def _harvest_body(body: list[ast.stmt], info: ClassInfo, hint_names: HintNames, branches: bool) -> None:
    """Add the definitions in a class *body* to *info*, following statically known ``if`` branches."""
    for child in body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.methods.append(harvest_function_node(child, hint_names))
        elif isinstance(child, ast.ClassDef):
            info.classes.append(harvest_class(child, hint_names, branches))
        elif isinstance(child, ast.If) and branches and is_version_test(child.test):
            _harvest_block(child, info, hint_names)
        elif isinstance(child, ast.If):
            _harvest_body(taken_branches(child), info, hint_names, branches)
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


def _harvest_block(node: ast.If, info: ClassInfo, hint_names: HintNames) -> None:
    """Harvest every branch of a version ``if`` in a class body, tagging the members with their branch."""
    chain = version_chain(node)
    block = VersionBlock(node.lineno, [unparse(t) for t, _ in chain], taken_index([t for t, _ in chain]))
    for index, (_, body) in enumerate(chain):
        before = (len(info.methods), len(info.attributes), len(info.classes))
        _harvest_body(body, info, hint_names, True)
        for items, start in zip((info.methods, info.attributes, info.classes), before, strict=True):
            for item in items[start:]:
                item.branch = ((block, index), *item.branch)
