"""
Docstring type inference for NumPy, Google and Sphinx / reST conventions.
"""
from __future__ import annotations

import inspect

from ._google import parse_google
from ._numpy import parse_numpy
from ._sphinx import parse_sphinx
from .models import DocstringTypes

__all__ = ["DocstringTypes", "parse_docstring_types"]


def parse_docstring_types(docstring: str | None) -> DocstringTypes:
    """Parse parameter and return types from a structured docstring.

    All three parsers run and their results are merged, Sphinx first, then
    Google, then NumPy, so mixed-style docstrings are fully covered.

    Parameters
    ----------
    docstring : str or None
        The docstring text.

    Returns
    -------
    DocstringTypes
        The parameter and return types found; empty for a missing or blank docstring.

    Examples
    --------
    >>> parse_docstring_types(None).is_empty()
    True
    >>> parse_docstring_types("Args:\\n    x (int): desc\\nReturns:\\n    float: value").params
    {'x': 'int'}
    """
    if not docstring or not docstring.strip():
        return DocstringTypes()
    docstring = inspect.cleandoc(docstring)
    return parse_sphinx(docstring).merge(parse_google(docstring)).merge(parse_numpy(docstring))
