"""Module-level directives: ``# stubpy: ignore`` and ``__all__``."""
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


def _string_items(node: ast.expr) -> list[str] | None:
    """Return the strings of a list/tuple display or a ``+`` of displays, else ``None``."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _string_items(node.left), _string_items(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, (ast.List, ast.Tuple)):
        return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return None


def extract_all_list(node: ast.Assign) -> list[str] | None:
    """Return the string items of ``__all__ = [...]`` (or a ``+`` of lists), or ``None``."""
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "__all__":
            return _string_items(node.value)
    return None


def extract_all_extension(node: ast.AugAssign) -> list[str] | None:
    """Return the string items added by ``__all__ += [...]``, or ``None``."""
    if isinstance(node.target, ast.Name) and node.target.id == "__all__" and isinstance(node.op, ast.Add):
        return _string_items(node.value)
    return None
