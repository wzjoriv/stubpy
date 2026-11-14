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


def extract_all_list(node: ast.Assign) -> list[str] | None:
    """Return the string items of an ``__all__ = [...]`` assignment, or ``None``."""
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "__all__":
            if isinstance(node.value, (ast.List, ast.Tuple)):
                result: list[str] = []
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        result.append(elt.value)
                return result
    return None
