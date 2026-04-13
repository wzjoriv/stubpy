"""
stubpy.docstring
================

Docstring type inference — parse parameter and return types from structured
docstrings when no explicit annotation is present.

Three docstring conventions are supported:

**NumPy style**::

    Parameters
    ----------
    x : int
        Description of x.
    items : list[str], optional
        Description of items.

    Returns
    -------
    float
        Description of the return value.

**Google style**::

    Args:
        x (int): Description of x.
        items (list[str], optional): Description of items.

    Returns:
        float: Description of the return value.

**Sphinx / reST style**::

    :param int x: Description of x.
    :type items: list[str]
    :returns: Description.
    :rtype: float

The public API is a single function: :func:`parse_docstring_types`.

Usage in stub generation
------------------------
When :attr:`~stubpy.context.StubConfig.infer_types_from_docstrings` is
``True`` and a parameter has no annotation, :func:`parse_docstring_types`
is called and any inferred type is emitted as an inline comment::

    def foo(
        x,   # type: int -- inferred from docstring
        y: str,
    ) -> None: ...

The ``# type:`` comment style keeps inferred types visually distinct from
developer-supplied annotations so the origin is always clear.

Multiple docstring formats in the same docstring are supported: all
parsers run and their results are *merged*, so a developer who uses
NumPy-style params but an ``:rtype:`` Sphinx return tag will get full
coverage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DocstringTypes:
    """Result of parsing one docstring for type information.

    Attributes
    ----------
    params : dict of str → str
        Mapping of parameter name to inferred type string.
    returns : str or None
        Inferred return type string, or ``None`` when absent.

    Examples
    --------
    >>> dt = DocstringTypes(params={"x": "int", "y": "str"}, returns="float")
    >>> dt.params["x"]
    'int'
    >>> dt.returns
    'float'
    """
    params:  dict[str, str] = field(default_factory=dict)
    returns: str | None     = None

    def is_empty(self) -> bool:
        """Return ``True`` when no type information was extracted.

        Examples
        --------
        >>> DocstringTypes().is_empty()
        True
        >>> DocstringTypes(params={"x": "int"}).is_empty()
        False
        """
        return not self.params and self.returns is None

    def merge(self, other: "DocstringTypes") -> "DocstringTypes":
        """Return a new :class:`DocstringTypes` merging *self* with *other*.

        *self*'s values take precedence; *other* fills gaps.

        Parameters
        ----------
        other : DocstringTypes
            The secondary result to fill in missing entries from.

        Returns
        -------
        DocstringTypes
            A merged result.

        Examples
        --------
        >>> a = DocstringTypes(params={"x": "int"}, returns=None)
        >>> b = DocstringTypes(params={"y": "str"}, returns="float")
        >>> m = a.merge(b)
        >>> sorted(m.params.items())
        [('x', 'int'), ('y', 'str')]
        >>> m.returns
        'float'
        """
        merged_params = dict(other.params)
        merged_params.update(self.params)  # self takes precedence
        return DocstringTypes(
            params=merged_params,
            returns=self.returns if self.returns is not None else other.returns,
        )


def parse_docstring_types(docstring: str | None) -> DocstringTypes:
    """Parse type information from a structured docstring.

    Runs NumPy, Google, and Sphinx/reST parsers and *merges* all results
    so mixed-style docstrings receive full coverage.

    Parameters
    ----------
    docstring : str or None
        Raw docstring text.  ``None`` or empty strings return an empty
        :class:`DocstringTypes`.

    Returns
    -------
    DocstringTypes
        Merged type information from all parsers.  May be empty if no
        types were found.

    Examples
    --------
    >>> parse_docstring_types(None).is_empty()
    True
    >>> result = parse_docstring_types(
    ...     "Args:\\n    x (int): desc\\n    y (str): desc\\nReturns:\\n    float: value"
    ... )
    >>> result.params
    {'x': 'int', 'y': 'str'}
    >>> result.returns
    'float'
    """
    if not docstring or not docstring.strip():
        return DocstringTypes()

    numpy_result  = _parse_numpy(docstring)
    google_result = _parse_google(docstring)
    sphinx_result = _parse_sphinx(docstring)

    # Merge all: sphinx -> google -> numpy (leftmost wins per key)
    result = sphinx_result.merge(google_result).merge(numpy_result)
    return result


# ---------------------------------------------------------------------------
# NumPy-style parser
# ---------------------------------------------------------------------------

# A section header: text on one line, dashes on the next
_NUMPY_DASHES = re.compile(r"^\s*-{3,}\s*$")

# "param_name : type" or "param_name : type, optional"
_NUMPY_PARAM_LINE = re.compile(
    r"^(?P<name>\w+)\s*:\s*(?P<type>[^\n,]+?)(?:\s*,\s*optional)?\s*$"
)


def _parse_numpy(doc: str) -> DocstringTypes:
    """Parse a NumPy-style docstring.

    Parameters
    ----------
    doc : str
        Raw docstring text.

    Returns
    -------
    DocstringTypes
        Parsed types.
    """
    result = DocstringTypes()
    lines = doc.expandtabs(4).splitlines()

    # Walk lines, identify section titles by detecting "---" on the next line
    sections: dict[str, list[str]] = {}
    current_title: str | None = None
    current_body: list[str] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and _NUMPY_DASHES.match(lines[i + 1]):
            # Save previous section
            if current_title is not None:
                sections[current_title.lower()] = current_body
            current_title = lines[i].strip()
            current_body = []
            i += 2  # skip title + dashes line
            continue
        if current_title is not None:
            current_body.append(lines[i])
        i += 1
    if current_title is not None:
        sections[current_title.lower()] = current_body

    # Parse Parameters-like sections
    param_section_names = (
        "parameters", "params", "other parameters",
        "keyword args", "keyword arguments",
    )
    for section_name in param_section_names:
        body = sections.get(section_name, [])
        for line in body:
            m = _NUMPY_PARAM_LINE.match(line.strip())
            if m:
                pname = m.group("name").strip()
                ptype = _clean_type(m.group("type").strip())
                if pname and ptype and pname not in result.params:
                    result.params[pname] = ptype

    # Parse Returns section — first non-empty, non-indented line is the type
    for section_name in ("returns", "return"):
        body = sections.get(section_name, [])
        for line in body:
            stripped = line.strip()
            if not stripped:
                continue
            # "name : type" or just "type"
            if ":" in stripped:
                parts = stripped.split(":", 1)
                ptype = _clean_type(parts[1].strip())
            else:
                ptype = _clean_type(stripped)
            if ptype:
                result.returns = ptype
            break  # only first non-empty line

    return result


# ---------------------------------------------------------------------------
# Google-style parser
# ---------------------------------------------------------------------------

# Section header: "Title:" at column 0 (no leading spaces)
_GOOGLE_SECTION = re.compile(r"^(?P<indent>\s*)(?P<title>[A-Za-z][A-Za-z ]*?):\s*$")

# "    param_name (type): description"
# "    param_name (type, optional): description"
_GOOGLE_PARAM = re.compile(
    r"^\s+(?P<name>\w+)\s*\((?P<type>[^)]+?)\)(?:\s*,\s*optional)?\s*:"
)

# "    type: description"  (returns section)
_GOOGLE_RETURN = re.compile(
    r"^\s+(?P<type>[A-Za-z_][A-Za-z0-9_\[\], |.]*?)\s*:"
)


def _parse_google(doc: str) -> DocstringTypes:
    """Parse a Google-style docstring.

    Parameters
    ----------
    doc : str
        Raw docstring text.

    Returns
    -------
    DocstringTypes
        Parsed types.
    """
    result = DocstringTypes()
    lines = doc.expandtabs(4).splitlines()

    sections: dict[str, list[str]] = {}
    current_title: str | None = None
    current_body: list[str] = []

    # Detect the base indentation from the first non-empty line
    base_indent = ""
    for line in lines:
        if line.strip():
            base_indent = line[: len(line) - len(line.lstrip())]
            break

    for line in lines:
        m = _GOOGLE_SECTION.match(line)
        if m:
            indent = m.group("indent")
            title = m.group("title").strip()
            # Accept as section header if at base indentation level
            if indent == base_indent:
                if current_title is not None:
                    sections[current_title.lower()] = current_body
                current_title = title
                current_body = []
                continue
        if current_title is not None:
            current_body.append(line)
    if current_title is not None:
        sections[current_title.lower()] = current_body

    param_section_names = (
        "args", "arguments", "parameters", "params",
        "keyword args", "keyword arguments", "other parameters",
    )
    for section_name in param_section_names:
        body = sections.get(section_name, [])
        for line in body:
            m = _GOOGLE_PARAM.match(line)
            if m:
                pname = m.group("name").strip()
                ptype = _clean_type(m.group("type").strip())
                if pname and ptype and pname not in result.params:
                    result.params[pname] = ptype

    for section_name in ("returns", "return"):
        body = sections.get(section_name, [])
        for line in body:
            m = _GOOGLE_RETURN.match(line)
            if m:
                ptype = _clean_type(m.group("type").strip())
                if ptype:
                    result.returns = ptype
                    break

    return result


# ---------------------------------------------------------------------------
# Sphinx / reST-style parser
# ---------------------------------------------------------------------------

# :param type name: description  (combined form)
_RST_PARAM_TYPED = re.compile(
    r"^\s*:param\s+(?P<type>\S+)\s+(?P<name>\w+)\s*:"
)
# :param name: description  (name-only; type in separate :type: directive)
_RST_PARAM_NAME = re.compile(
    r"^\s*:param\s+(?P<name>\w+)\s*:"
)
# :type name: type
_RST_TYPE = re.compile(
    r"^\s*:type\s+(?P<name>\w+)\s*:\s*(?P<type>.+)"
)
# :rtype: type
_RST_RTYPE = re.compile(
    r"^\s*:rtype\s*:\s*(?P<type>.+)"
)


def _parse_sphinx(doc: str) -> DocstringTypes:
    """Parse a Sphinx / reST-style docstring.

    Supported field-list directives::

        :param int x: Description of x.
        :type items: list[str]
        :returns: Description.
        :rtype: float

    Parameters
    ----------
    doc : str
        Raw docstring text.

    Returns
    -------
    DocstringTypes
        Parsed types.
    """
    result = DocstringTypes()
    type_overrides: dict[str, str] = {}

    for line in doc.splitlines():
        # :param type name: ...
        m = _RST_PARAM_TYPED.match(line)
        if m:
            pname = m.group("name").strip()
            ptype = _clean_type(m.group("type").strip())
            if pname and ptype:
                result.params.setdefault(pname, ptype)
            continue

        # :param name: ...
        m = _RST_PARAM_NAME.match(line)
        if m:
            pname = m.group("name").strip()
            if pname:
                result.params.setdefault(pname, "")  # placeholder
            continue

        # :type name: type
        m = _RST_TYPE.match(line)
        if m:
            pname = m.group("name").strip()
            ptype = _clean_type(m.group("type").strip())
            if pname and ptype:
                type_overrides[pname] = ptype
            continue

        # :rtype: type
        m = _RST_RTYPE.match(line)
        if m:
            ptype = _clean_type(m.group("type").strip())
            if ptype and result.returns is None:
                result.returns = ptype
            continue

    # Apply :type: overrides (always take precedence over :param type name:)
    for pname, ptype in type_overrides.items():
        result.params[pname] = ptype

    # Drop placeholder entries (param declared but no type found anywhere)
    result.params = {k: v for k, v in result.params.items() if v}

    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

_MULTI_SPACE = re.compile(r"\s+")

# Common English words that, when found as the first word of a "type" field,
# strongly suggest the field is actually a description sentence, not a type.
_DESCRIPTION_WORDS = frozenset({
    "a", "an", "the", "this", "if", "when", "whether", "description",
    "note", "see", "optional", "required", "default", "used", "whether",
    "called", "whether", "will", "can", "may", "should", "must",
})


def _clean_type(raw: str) -> str:
    """Normalise a raw type string extracted from a docstring.

    - Strips outer whitespace and collapses internal whitespace.
    - Converts ``X or None`` / ``X or Y`` to ``X | None`` / ``X | Y``.
    - Returns ``""`` for strings that look like descriptions rather than
      type names.

    Parameters
    ----------
    raw : str
        Raw type string from the docstring.

    Returns
    -------
    str
        Cleaned type string, or ``""`` if *raw* does not look like a type.

    Examples
    --------
    >>> _clean_type("  list[str]  ")
    'list[str]'
    >>> _clean_type("a description sentence")
    ''
    >>> _clean_type("int or None")
    'int | None'
    """
    raw = raw.strip()
    if not raw:
        return ""

    # "X or None" / "X or Y" → "X | None" / "X | Y"
    raw = re.sub(r"\bor\b", "|", raw)
    raw = re.sub(r"\s*\|\s*", " | ", raw)

    # Collapse whitespace
    raw = _MULTI_SPACE.sub(" ", raw).strip()

    # Strip trailing "optional" / ", optional"
    raw = re.sub(r",?\s*optional$", "", raw, flags=re.IGNORECASE).strip()

    if not raw:
        return ""

    # Heuristic: starts with a description word → not a type
    first = raw.split()[0].lower().rstrip(".,;:")
    if first in _DESCRIPTION_WORDS:
        return ""

    # Heuristic: if it looks like a union (has |), count union members not tokens.
    # Otherwise count space-separated tokens outside brackets.
    without_brackets = re.sub(r"\[.*?\]", "", raw)
    if "|" in without_brackets:
        # Each member may have internal spaces from generic args; count | separators
        member_count = without_brackets.count("|") + 1
        if member_count > 8:  # very long union → likely a description
            return ""
    elif len(without_brackets.split()) > 4:
        return ""

    return raw
