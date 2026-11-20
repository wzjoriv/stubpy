"""
The string choices a :class:`Config` option takes: union, alias and version-branch styles.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class _Choice(str, Enum):
    """A string-valued enum that also accepts its value, case-insensitively."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def coerce(cls, value: Any, option: str) -> Any:
        """Return the member for *value* (a member or its string value); raise ``ValueError`` otherwise."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            for member in cls:
                if member.value == value.strip().lower():
                    return member
        allowed = ", ".join(repr(m.value) for m in cls)
        raise ValueError(f"Invalid {option}: {value!r}; expected one of {allowed}")


class UnionStyle(_Choice):
    """How unions are written.

    Attributes
    ----------
    MODERN
        PEP 604: ``int | None``.  The default.
    LEGACY
        ``Optional[int]`` and ``Union[int, str]``.

    Examples
    --------
    >>> UnionStyle("legacy") is UnionStyle.LEGACY
    True
    >>> str(UnionStyle.MODERN)
    'modern'
    """
    MODERN = "modern"
    LEGACY = "legacy"


class AliasStyle(_Choice):
    """How type aliases are written.

    Attributes
    ----------
    COMPATIBLE
        ``Name: TypeAlias = rhs``.  The default.
    PEP695
        ``type Name = rhs`` (readable by Python 3.12+ tools).
    AUTO
        ``PEP695`` when stubpy runs on Python 3.12+, else ``COMPATIBLE``.

    Examples
    --------
    >>> AliasStyle("pep695") is AliasStyle.PEP695
    True
    >>> str(AliasStyle.COMPATIBLE)
    'compatible'
    """
    COMPATIBLE = "compatible"
    PEP695 = "pep695"
    AUTO = "auto"


class VersionBranches(_Choice):
    """What happens to ``if`` statements testing ``sys.version_info`` or ``sys.platform``.

    Attributes
    ----------
    EMIT
        Copy the ``if`` / ``elif`` / ``else`` into the stub, each branch with
        the stubs of the names it defines, as typeshed does.  The default.
    RESOLVE
        Keep only the branch the running interpreter takes.

    Examples
    --------
    >>> VersionBranches("resolve") is VersionBranches.RESOLVE
    True
    >>> str(VersionBranches.EMIT)
    'emit'
    """
    EMIT = "emit"
    RESOLVE = "resolve"
