"""Stub layout: the stub's sections and its own ``__all__``."""
from __future__ import annotations

import ast

from stubpy._constants import IMPORT_LINE_LIMIT


def stub_text(header: str, exported: str, body: str) -> str:
    """Join the import header, the ``__all__`` block and the body, skipping empty sections.

    Examples
    --------
    >>> stub_text("", "", "def f(): ...")
    'def f(): ...\\n'
    """
    sections = [s for s in (header, exported, body) if s]
    return "\n\n".join(sections) + "\n" if sections else ""


def _bound_names(text: str) -> set[str]:
    """Return the module-level names *text* (stub source) binds through imports and definitions, version branches included."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    nodes = list(tree.body)
    while nodes:
        node = nodes.pop(0)
        if isinstance(node, ast.If):
            nodes[:0] = node.body + node.orelse
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names if a.name != "*")
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif type(node).__name__ == "TypeAlias":
            names.add(node.name.id)  # type: ignore[attr-defined]
    return names


def all_block(order: list[str], header: str, body: str) -> str:
    """Return the stub's ``__all__ = [...]``: the module's ``__all__`` names the stub binds; ``""`` without any.

    Examples
    --------
    >>> all_block(["f", "missing"], "", "def f(): ...")
    '__all__ = ["f"]'
    """
    if not order:
        return ""
    bound = _bound_names(header + "\n" + body)
    names = [n for n in order if n in bound]
    if not names:
        return ""
    line = "__all__ = [" + ", ".join(f'"{n}"' for n in names) + "]"
    if len(line) <= IMPORT_LINE_LIMIT:
        return line
    return "__all__ = [\n" + "".join(f'    "{n}",\n' for n in names) + "]"
