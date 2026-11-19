"""
Sphinx / reST field-list docstring parsing.
"""
from __future__ import annotations

import re

from ._clean import clean_type
from .models import DocstringTypes

_RST_PARAM_TYPED = re.compile(r"^\s*:param\s+(?P<type>\S+)\s+(?P<name>\w+)\s*:")
_RST_PARAM_NAME = re.compile(r"^\s*:param\s+(?P<name>\w+)\s*:")
_RST_TYPE = re.compile(r"^\s*:type\s+(?P<name>\w+)\s*:\s*(?P<type>.+)")
_RST_RTYPE = re.compile(r"^\s*:rtype\s*:\s*(?P<type>.+)")


def parse_sphinx(doc: str) -> DocstringTypes:
    """Parse ``:param type name:``, ``:type name:`` and ``:rtype:`` fields."""
    result = DocstringTypes()
    type_overrides: dict[str, str] = {}

    for line in doc.splitlines():
        m = _RST_PARAM_TYPED.match(line)
        if m:
            pname = m.group("name").strip()
            ptype = clean_type(m.group("type").strip())
            if pname and ptype:
                result.params.setdefault(pname, ptype)
            continue

        m = _RST_PARAM_NAME.match(line)
        if m:
            pname = m.group("name").strip()
            if pname:
                result.params.setdefault(pname, "")
            continue

        m = _RST_TYPE.match(line)
        if m:
            pname = m.group("name").strip()
            ptype = clean_type(m.group("type").strip())
            if pname and ptype:
                type_overrides[pname] = ptype
            continue

        m = _RST_RTYPE.match(line)
        if m:
            ptype = clean_type(m.group("type").strip())
            if ptype and result.returns is None:
                result.returns = ptype
            continue

    for pname, ptype in type_overrides.items():
        result.params[pname] = ptype

    result.params = {k: v for k, v in result.params.items() if v}
    return result
