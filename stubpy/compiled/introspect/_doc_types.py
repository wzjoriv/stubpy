"""
Types and per-overload texts read from binding docstrings.
"""
from __future__ import annotations

import re

_ATTR_RE = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*$")
_RETURNS_RE = re.compile(r"^\s*(?:\w+)?\(.*\)\s*->\s*(.+?)\s*$")
_NUMBERED_RE = re.compile(r"^\s*(\d+)\.\s+\w[\w.]*\(.*$")


def doc_type(name: str, doc: object) -> str | None:
    """Return the type a getset / member docstring states: a ``name: T`` line or a ``(...) -> T`` line."""
    if not isinstance(doc, str):
        return None
    for line in doc.strip().splitlines()[:3]:
        attr = _ATTR_RE.match(line)
        if attr and attr.group(1) == name:
            return attr.group(2)
        returns = _RETURNS_RE.match(line)
        if returns:
            return returns.group(1)
    return None


def variant_docs(doc: object) -> list[str]:
    """Return the text under each ``1. f(...)`` line of a pybind11 ``Overloaded function.`` docstring."""
    if not isinstance(doc, str) or "Overloaded function." not in doc:
        return []
    out: list[list[str]] = []
    for line in doc.splitlines():
        if _NUMBERED_RE.match(line):
            out.append([])
        elif out:
            out[-1].append(line)
    return ["\n".join(lines).strip() for lines in out]
