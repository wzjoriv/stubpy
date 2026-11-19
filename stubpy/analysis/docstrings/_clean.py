"""
Normalisation of type strings pulled from docstrings.
"""
from __future__ import annotations

import re

_MULTI_SPACE = re.compile(r"\s+")

_DESCRIPTION_WORDS = frozenset({
    "a", "an", "the", "this", "if", "when", "whether", "description",
    "note", "see", "optional", "required", "default", "used", "called", "will", "can", "may", "should", "must",
})


def clean_type(raw: str) -> str:
    """Normalise a docstring type; return ``""`` when it reads like prose.

    ``X or Y`` becomes ``X | Y`` and a trailing ``optional`` is dropped.

    Examples
    --------
    >>> clean_type("int or None")
    'int | None'
    >>> clean_type("a description sentence")
    ''
    """
    raw = raw.strip()
    if not raw:
        return ""

    raw = re.sub(r"\bor\b", "|", raw)
    raw = re.sub(r"\s*\|\s*", " | ", raw)
    raw = _MULTI_SPACE.sub(" ", raw).strip()
    raw = re.sub(r",?\s*optional$", "", raw, flags=re.IGNORECASE).strip()

    if not raw:
        return ""

    first = raw.split()[0].lower().rstrip(".,;:")
    if first in _DESCRIPTION_WORDS:
        return ""

    without_brackets = re.sub(r"\[.*?\]", "", raw)
    if "|" in without_brackets:
        if without_brackets.count("|") + 1 > 8:
            return ""
    elif len(without_brackets.split()) > 4:
        return ""

    return raw
