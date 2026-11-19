"""
Docstrings written back as Python string literals (stub bodies, docstring sync).
"""
from __future__ import annotations

import inspect

__all__ = ["docstring_literal"]


def docstring_literal(doc: str | None, indent: str, newline: str = "\n") -> str | None:
    """Return *doc* as a PEP 257 triple-quoted literal whose continuation lines are indented by *indent*.

    Parameters
    ----------
    doc : str or None
        The docstring text.
    indent : str
        Indentation for every line after the first.
    newline : str, optional
        Line separator to write. Defaults to ``"\\n"``.

    Returns
    -------
    str or None
        The literal, or ``None`` for an empty docstring.

    Examples
    --------
    >>> docstring_literal("Summary.", "    ")
    '\"\"\"Summary.\"\"\"'
    >>> print(docstring_literal("Summary.\\n\\nDetails.", "    "))
    \"\"\"Summary.
    <BLANKLINE>
        Details.
        \"\"\"
    """
    if not isinstance(doc, str) or not doc.strip():
        return None
    cleaned = inspect.cleandoc(doc)
    cleaned = cleaned.replace("\\", "\\\\").replace('"""', r'\"\"\"')
    if cleaned.endswith('"'):
        cleaned = cleaned[:-1] + '\\"'
    lines = cleaned.splitlines()
    if len(lines) == 1:
        return f'"""{cleaned}"""'
    rest = "".join(f"{newline}{indent}{line}" if line.strip() else newline for line in lines[1:])
    return f'"""{lines[0]}{rest}{newline}{indent}"""'
