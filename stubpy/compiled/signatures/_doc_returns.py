"""
Return types a docstring states in prose or in a ``Returns`` section, for callables without annotations.
"""
from __future__ import annotations

import re
import textwrap

from stubpy.compiled._constants import DOC_RETURN_WORDS

from ._text import normalize_type

__all__ = ["doc_return_type"]

_RTYPE = re.compile(r"^\s*:rtype:\s*(.+?)\s*$", re.M)
_SECTION = re.compile(r"^(Returns?)\s*:?\s*$")
_RULE = re.compile(r"^[-=]{3,}\s*$")
_SENTENCE = re.compile(r"\breturns?\s+(?:a|an|the)?\s*(\w+)\b(?!\s+or\b)", re.I)
_WORD = re.compile(r"^(\w+)\b(?!\s+or\b)")


def _named(word: str | None) -> str | None:
    return DOC_RETURN_WORDS.get(word.lower()) if word else None


def _expression(text: str) -> str | None:
    """*text* when it is a type expression of known names (``list[int]``, ``int | None``), else ``None``."""
    found = normalize_type(text)
    names = re.findall(r"[A-Za-z_][\w]*", found or "")
    return found if found and names and all(n.lower() in DOC_RETURN_WORDS or n == "None" for n in names) else None


def _section_entry(lines: list[str]) -> str | None:
    """The first line under a ``Returns`` heading, ``None`` when there is no such section."""
    for i, line in enumerate(lines):
        if _SECTION.match(line.strip()):
            rest = [ln for ln in lines[i + 1:] if ln.strip() and not _RULE.match(ln.strip())]
            return rest[0].strip() if rest else None
    return None


def doc_return_type(doc: object) -> str | None:
    """The return type a docstring states, or ``None``.

    Reads ``:rtype:``, the first line of a ``Returns`` section (``list of paths``, ``int: count``) and a
    leading ``Returns a list`` sentence.

    Parameters
    ----------
    doc : object
        The docstring; anything else gives ``None``.

    Returns
    -------
    str or None
        The annotation text.

    Examples
    --------
    >>> doc_return_type("Sum.\n\nReturns:\n    list of values")
    'list'
    >>> doc_return_type("Close it.\n\n:rtype: bool")
    'bool'
    >>> doc_return_type("Something.") is None
    True
    """
    if not isinstance(doc, str):
        return None
    text = textwrap.dedent(doc.strip("\n"))
    declared = _RTYPE.search(text)
    if declared:
        return _expression(declared.group(1))
    entry = _section_entry(text.splitlines())
    if entry:
        _, colon, tail = entry.partition(" : ")
        typed = tail if colon else entry.partition(":")[0]
        word = _WORD.match(entry)
        return _expression(typed) or _expression(entry) or _named(word.group(1) if word else None)
    sentence = _SENTENCE.search(text.partition("\n\n")[0])
    return _named(sentence.group(1) if sentence else None)
