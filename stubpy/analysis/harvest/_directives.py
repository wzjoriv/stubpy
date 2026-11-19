"""
Module-level directives: ``# stubpy: ignore`` and ``__all__``.
"""
from __future__ import annotations

import ast
import re

_IGNORE_RE = re.compile(r"#\s*stubpy\s*:\s*ignore\b", re.IGNORECASE)


def has_ignore_directive(source: str) -> bool:
    """Return ``True`` if a ``# stubpy: ignore`` comment precedes the first code line.

    Examples
    --------
    >>> has_ignore_directive("# STUBPY: IGNORE\\nclass Foo: pass\\n")
    True
    >>> has_ignore_directive("class Foo: pass\\n# stubpy: ignore")
    False
    """
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if _IGNORE_RE.search(stripped):
                return True
            continue
        break
    return False


def _all_items(node: ast.expr) -> tuple[list[str], list[str]] | None:
    """Return ``(strings, spliced_names)`` of a list/tuple display or a ``+`` of displays, else ``None``.

    ``*name`` entries are spliced names; any other non-string entry makes the result ``None``.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _all_items(node.left), _all_items(node.right)
        if left is None or right is None:
            return None
        return left[0] + right[0], left[1] + right[1]
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    strings: list[str] = []
    spliced: list[str] = []
    for e in node.elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            strings.append(e.value)
        elif isinstance(e, ast.Starred) and isinstance(e.value, ast.Name):
            spliced.append(e.value.id)
        else:
            return None
    return strings, spliced


def extract_all(node: ast.Assign) -> tuple[list[str], list[str]] | None:
    """Return ``(strings, spliced_names)`` of ``__all__ = [..., *other_all]``, or ``None``."""
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "__all__":
            return _all_items(node.value)
    return None


def extract_all_list(node: ast.Assign) -> list[str] | None:
    """Return the string items of ``__all__ = [...]`` (or a ``+`` of lists), or ``None``."""
    items = extract_all(node)
    return items[0] if items is not None else None


def extract_all_extension(node: ast.AugAssign) -> tuple[list[str], list[str]] | None:
    """Return the ``(strings, spliced_names)`` added by ``__all__ += [...]``, or ``None``."""
    if isinstance(node.target, ast.Name) and node.target.id == "__all__" and isinstance(node.op, ast.Add):
        return _all_items(node.value)
    return None
