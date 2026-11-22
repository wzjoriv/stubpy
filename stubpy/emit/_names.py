"""
Names a stub can declare.
"""
from __future__ import annotations

import ast
import keyword


def declarable(name: str) -> bool:
    """True when *name* can be declared in a stub: an identifier that is not a keyword.

    Attributes set with ``setattr`` or listed in ``__slots__`` can be named ``return`` or
    ``my-field``; a stub cannot spell those.

    Examples
    --------
    >>> declarable("value"), declarable("return"), declarable("my-field")
    (True, False, False)
    """
    return name.isidentifier() and not keyword.iskeyword(name)


def bare_final_default(annotation: str, value: str | None = None) -> str:
    """The initializer a bare ``Final`` needs (a type checker infers its type from it), else ``""``.

    A short literal *value* from the source is kept, so the inferred type is the real one; anything else
    is written ``...``.

    Examples
    --------
    >>> bare_final_default("Final"), bare_final_default("Final[int]"), bare_final_default("Final", "'#text'")
    (' = ...', '', " = '#text'")
    """
    if annotation.strip() not in ("Final", "typing.Final", "typing_extensions.Final"):
        return ""
    return f" = {value}" if value is not None and _short_literal(value) else " = ..."


def _short_literal(text: str) -> bool:
    if len(text) > 60 or "\n" in text:
        return False
    try:
        ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False
    return True
