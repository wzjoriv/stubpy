"""
Normalisation of type strings pulled from docstrings.
"""
from __future__ import annotations

import ast
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

    text = " | ".join(_prose(part) for part in _top_level_commas_to_union(raw).split(" | "))
    try:
        ast.parse(text, mode="eval")
    except SyntaxError:
        return ""
    return text


def _top_level_commas_to_union(raw: str) -> str:
    """``None, bool | dict`` (a NumPy list of alternatives) as ``None | bool | dict``; commas in brackets stay.

    Examples
    --------
    >>> _top_level_commas_to_union("None, bool | dict"), _top_level_commas_to_union("dict[str, int]")
    ('None | bool | dict', 'dict[str, int]')
    """
    depth, out = 0, []
    for ch in raw:
        depth += ch in "[({"
        depth -= ch in "])}"
        out.append(" |" if ch == "," and depth == 0 else ch)
    return re.sub(r"\s*\|\s*", " | ", "".join(out)).strip()


_CONTAINERS = {
    "list": "list", "tuple": "tuple", "set": "set", "frozenset": "frozenset",
    "sequence": "Sequence", "iterable": "Iterable", "iterator": "Iterator",
}
_WORDS = {"callable": "Callable", "function": "Callable", "iterable": "Iterable", "iterator": "Iterator",
          "sequence": "Sequence", "mapping": "Mapping", "any": "Any", "boolean": "bool", "integer": "int",
          "string": "str"}
_CONTAINER_OF = re.compile(r"^(?P<kind>[A-Za-z]+) of (?P<item>.+)$")
_CHOICES = re.compile(r"^\{(?P<items>[^{}]+)\}$")
_CHOICE = re.compile(r"""^(?:'[^']*'|"[^"]*"|-?\d+|None|True|False)$""")


def _prose(part: str) -> str:
    """Turn the NumPy prose forms ``list of str``, ``tuple of (int, int)`` and ``{'a', 'b'}`` into annotations.

    Examples
    --------
    >>> _prose("list of str"), _prose("tuple of (int, float)"), _prose("{'fast', 'slow'}")
    ('list[str]', 'tuple[int, float]', "Literal['fast', 'slow']")
    >>> _prose("str")
    'str'
    """
    if part.lower() in _WORDS:
        return _WORDS[part.lower()]
    m = _CHOICES.match(part)
    if m:
        items = [i.strip() for i in m["items"].split(",") if i.strip()]
        return f"Literal[{', '.join(items)}]" if items and all(_CHOICE.match(i) for i in items) else part
    m = _CONTAINER_OF.match(part)
    if m and m["kind"].lower() in _CONTAINERS:
        item = m["item"].strip()
        if item.startswith("(") and item.endswith(")"):
            item = item[1:-1]
        items = [_prose(i.strip()) for i in item.split(",")]
        return f"{_CONTAINERS[m['kind'].lower()]}[{', '.join(items)}]"
    return part
