"""Docstring embedding for ``include_docstrings`` stubs."""
from __future__ import annotations

from stubpy.analysis.docstrings.literal import docstring_literal


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
    return docstring_block(getattr(obj, "__doc__", None), indent)


def docstring_block(doc: str | None, indent: str) -> str:
    """Return *doc* as a triple-quoted block indented by *indent*, or ``"..."`` when it is empty."""
    return docstring_literal(doc, indent) or "..."
