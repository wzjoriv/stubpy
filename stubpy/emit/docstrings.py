"""Docstring embedding for ``include_docstrings`` stubs."""
from __future__ import annotations

import inspect


def make_docstring_body(obj: object, indent: str) -> str:
    """Return *obj*'s docstring as a PEP 257 triple-quoted block indented by *indent*, or ``"..."``.

    Examples
    --------
    >>> def f():
    ...     '''Summary.
    ...
    ...     Details.
    ...     '''
    >>> print(make_docstring_body(f, "    "))
    \"\"\"Summary.
    <BLANKLINE>
        Details.
        \"\"\"
    """
    doc = getattr(obj, "__doc__", None)
    if not isinstance(doc, str) or not doc.strip():
        return "..."
    cleaned = inspect.cleandoc(doc)
    cleaned = cleaned.replace("\\", "\\\\").replace('"""', r'\"\"\"')
    if cleaned.endswith('"'):
        cleaned = cleaned[:-1] + '\\"'
    lines = cleaned.splitlines()
    if len(lines) == 1:
        return f'"""{cleaned}"""'
    rest = "".join(f"\n{indent}{line}" if line.strip() else "\n" for line in lines[1:])
    return f'"""{lines[0]}{rest}\n{indent}"""'
