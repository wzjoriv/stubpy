"""
Docstring embedding for ``include_docstrings`` stubs.
"""
from __future__ import annotations

from stubpy.analysis.docstrings.literal import docstring_literal


def make_docstring_body(obj: object, indent: str) -> str:
    """Return an object's docstring as a PEP 257 block, or ``"..."``.

    The block is triple-quoted and indented by *indent*; an object without a
    docstring gives ``"..."``.

    Parameters
    ----------
    obj : object
        The object whose ``__doc__`` is embedded.
    indent : str
        The indentation of the block's continuation lines.

    Returns
    -------
    str
        The docstring block, or ``"..."``.

    See Also
    --------
    docstring_block : Formats a docstring given as text.

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
    """Return *doc* as a triple-quoted block, or ``"..."`` when it is empty.

    Parameters
    ----------
    doc : str or None
        The docstring text.
    indent : str
        The indentation of the block's continuation lines.

    Returns
    -------
    str
        The docstring block, or ``"..."``.

    See Also
    --------
    make_docstring_body : Takes the docstring from an object.

    Examples
    --------
    >>> docstring_block(None, "    ")
    '...'
    """
    return docstring_literal(doc, indent) or "..."
