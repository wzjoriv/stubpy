"""
Syntactic recognition of ``stubpy.hint`` decorators.
"""
from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from stubpy.analysis._constants import (
    COPY_FUNCTIONS,
    HINT_DECORATORS,
    HINT_DEFAULT_PREFIXES,
    HINT_MODULE,
    STATEMENT_BLOCK_FIELDS,
)

from ._nodes import unparse


@dataclass
class HintNames:
    """How the hint decorators are spelled in one module, plus the bare names bound to copy-with-changes functions."""
    prefixes: set[str] = field(default_factory=lambda: set(HINT_DEFAULT_PREFIXES))
    direct: dict[str, str] = field(default_factory=dict)
    copiers: set[str] = field(default_factory=set)


@dataclass
class Hints:
    """The hints found on one definition."""
    signature: str | None = None
    returns: str | None = None
    ignore: bool = False


def hint_names(tree: ast.Module | None) -> HintNames:
    """Collect the local spellings of ``stubpy.hint`` from the imports in *tree*."""
    names = HintNames()
    if tree is None:
        return names
    package, _, module = HINT_MODULE.rpartition(".")
    for node in _statements(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package and alias.asname:
                    names.prefixes.add(f"{alias.asname}.{module}")
                elif alias.name == HINT_MODULE and alias.asname:
                    names.prefixes.add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            for alias in node.names:
                if node.module == package and alias.name == module:
                    names.prefixes.add(alias.asname or module)
                elif node.module == HINT_MODULE and alias.name in HINT_DECORATORS:
                    names.direct[alias.asname or alias.name] = alias.name
                elif COPY_FUNCTIONS.get(node.module or "") == alias.name:
                    names.copiers.add(alias.asname or alias.name)
    return names


def _statements(tree: ast.Module) -> Iterator[ast.AST]:
    """Yield the statement-level nodes of *tree* in :func:`ast.walk` order, skipping expressions."""
    todo: deque[ast.AST] = deque([tree])
    while todo:
        node = todo.popleft()
        for name in STATEMENT_BLOCK_FIELDS:
            todo.extend(getattr(node, name, ()))
        yield node


def split_hints(decorators: list[ast.expr], names: HintNames) -> tuple[list[ast.expr], Hints]:
    """Return the decorators that are not hints, and the hints read from the rest."""
    kept: list[ast.expr] = []
    hints = Hints()
    for node in decorators:
        kind = _hint_kind(node.func if isinstance(node, ast.Call) else node, names)
        if kind is None:
            kept.append(node)
            continue
        if kind == "ignore":
            hints.ignore = True
            continue
        text = _string_arg(node)
        if kind == "signature" and text is not None and text.strip().startswith("("):
            hints.signature = text.strip()
        elif kind == "returns" and text is not None:
            hints.returns = text.strip()
    return kept, hints


def _hint_kind(func: ast.expr, names: HintNames) -> str | None:
    """Return ``"signature"`` / ``"returns"`` / ``"ignore"`` when *func* names a hint decorator."""
    dotted = unparse(func) or ""
    if dotted in names.direct:
        return names.direct[dotted]
    prefix, _, attr = dotted.rpartition(".")
    if prefix in names.prefixes and attr in HINT_DECORATORS:
        return attr
    return None


def _string_arg(node: ast.expr) -> str | None:
    """Return the first argument of a call when it is a string literal."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    arg = node.args[0]
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
