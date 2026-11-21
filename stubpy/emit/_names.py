"""
Names a stub can declare.
"""
from __future__ import annotations

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


def bare_final_default(annotation: str) -> str:
    """``" = ..."`` for a bare ``Final`` (a type checker needs an initializer to infer its type), else ``""``.

    Examples
    --------
    >>> bare_final_default("Final"), bare_final_default("Final[int]")
    (' = ...', '')
    """
    return " = ..." if annotation.strip() in ("Final", "typing.Final", "typing_extensions.Final") else ""
