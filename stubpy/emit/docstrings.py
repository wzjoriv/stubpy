"""Docstring embedding for ``include_docstrings`` stubs."""
from __future__ import annotations

import textwrap


def make_docstring_body(obj: object, indent: str) -> str:
    """Return *obj*'s docstring as a triple-quoted block indented by *indent*, or ``"..."``."""
    doc = getattr(obj, "__doc__", None)
    if not doc or not doc.strip():
        return "..."
    cleaned = textwrap.dedent(doc).strip()
    cleaned = cleaned.replace('"""', r'\"\"\"')
    lines = cleaned.splitlines()
    if len(lines) == 1 and len(cleaned) < 72:
        return f'"""{cleaned}"""'
    inner = ("\n" + indent).join(lines)
    return f'"""\n{indent}{inner}\n{indent}"""'
