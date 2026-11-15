"""Stub layout: joining emitted symbol stubs into a body, and the stub's own ``__all__``."""
from __future__ import annotations

import ast

from stubpy._constants import IMPORT_LINE_LIMIT


def join_sections(tagged: list[tuple[str, bool]]) -> str:
    """Join ``(stub, is_compact)`` pairs: one newline between compact stubs, a blank line otherwise.

    Examples
    --------
    >>> join_sections([("X: int", True), ("Y: str", True), ("def f(): ...", False)])
    'X: int\\nY: str\\n\\ndef f(): ...'
    """
    if not tagged:
        return ""
    parts = [tagged[0][0]]
    for (_, prev_compact), (text, curr_compact) in zip(tagged, tagged[1:], strict=False):
        sep = "\n" if (prev_compact and curr_compact) else "\n\n"
        parts.append(sep + text)
    return "".join(parts)


def _bound_names(text: str) -> set[str]:
    """Return the top-level names *text* (stub source) binds through imports and definitions."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
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
