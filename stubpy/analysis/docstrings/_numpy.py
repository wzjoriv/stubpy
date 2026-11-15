"""NumPy-style docstring parsing."""
from __future__ import annotations

import re

from ._clean import clean_type
from .models import DocstringTypes

_NUMPY_DASHES = re.compile(r"^\s*-{3,}\s*$")

_NUMPY_PARAM_LINE = re.compile(
    r"^(?P<name>\w+)\s*:\s*(?P<type>[^\n,]+?)(?:\s*,\s*optional)?\s*$"
)

_PARAM_SECTIONS = (
    "parameters", "params", "other parameters",
    "keyword args", "keyword arguments",
)


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Split *lines* into sections keyed by lower-cased title (a title is underlined by dashes)."""
    sections: dict[str, list[str]] = {}
    current_title: str | None = None
    current_body: list[str] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and _NUMPY_DASHES.match(lines[i + 1]):
            if current_title is not None:
                sections[current_title.lower()] = current_body
            current_title = lines[i].strip()
            current_body = []
            i += 2
            continue
        if current_title is not None:
            current_body.append(lines[i])
        i += 1
    if current_title is not None:
        sections[current_title.lower()] = current_body
    return sections


def parse_numpy(doc: str) -> DocstringTypes:
    """Parse parameter and return types from a NumPy-style docstring."""
    result = DocstringTypes()
    sections = _split_sections(doc.expandtabs(4).splitlines())

    for section_name in _PARAM_SECTIONS:
        for line in sections.get(section_name, []):
            m = _NUMPY_PARAM_LINE.match(line.strip())
            if m:
                pname = m.group("name").strip()
                ptype = clean_type(m.group("type").strip())
                if pname and ptype and pname not in result.params:
                    result.params[pname] = ptype

    for section_name in ("returns", "return"):
        for line in sections.get(section_name, []):
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped:
                ptype = clean_type(stripped.split(":", 1)[1].strip())
            else:
                ptype = clean_type(stripped)
            if ptype:
                result.returns = ptype
            break

    return result
