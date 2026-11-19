"""
Google-style docstring parsing.
"""
from __future__ import annotations

import re

from ._clean import clean_type
from .models import DocstringTypes

_GOOGLE_SECTION = re.compile(r"^(?P<indent>\s*)(?P<title>[A-Za-z][A-Za-z ]*?):\s*$")

_GOOGLE_PARAM = re.compile(
    r"^\s+(?P<name>\w+)\s*\((?P<type>[^)]+?)\)(?:\s*,\s*optional)?\s*:"
)

_GOOGLE_RETURN = re.compile(
    r"^\s+(?P<type>[A-Za-z_][A-Za-z0-9_\[\], |.]*?)\s*:"
)

_PARAM_SECTIONS = (
    "args", "arguments", "parameters", "params",
    "keyword args", "keyword arguments", "other parameters",
)


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Split *lines* into sections keyed by lower-cased ``Title:`` at the base indentation."""
    sections: dict[str, list[str]] = {}
    current_title: str | None = None
    current_body: list[str] = []

    base_indent = ""
    for line in lines:
        if line.strip():
            base_indent = line[: len(line) - len(line.lstrip())]
            break

    for line in lines:
        m = _GOOGLE_SECTION.match(line)
        if m and m.group("indent") == base_indent:
            if current_title is not None:
                sections[current_title.lower()] = current_body
            current_title = m.group("title").strip()
            current_body = []
            continue
        if current_title is not None:
            current_body.append(line)
    if current_title is not None:
        sections[current_title.lower()] = current_body
    return sections


def parse_google(doc: str) -> DocstringTypes:
    """Parse parameter and return types from a Google-style docstring."""
    result = DocstringTypes()
    sections = _split_sections(doc.expandtabs(4).splitlines())

    for section_name in _PARAM_SECTIONS:
        for line in sections.get(section_name, []):
            m = _GOOGLE_PARAM.match(line)
            if m:
                pname = m.group("name").strip()
                ptype = clean_type(m.group("type").strip())
                if pname and ptype and pname not in result.params:
                    result.params[pname] = ptype

    for section_name in ("returns", "return"):
        for line in sections.get(section_name, []):
            m = _GOOGLE_RETURN.match(line)
            if m:
                ptype = clean_type(m.group("type").strip())
                if ptype:
                    result.returns = ptype
                    break

    return result
