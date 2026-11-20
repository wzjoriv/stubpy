"""
Which Python release a source needs, judged from syntax the running interpreter cannot parse.
"""
from __future__ import annotations

import re
import sys

from stubpy.analysis._constants import NEWER_SYNTAX

__all__ = ["NewerSyntaxError", "required_python"]

_PATTERNS = [(version, re.compile(pattern, re.MULTILINE), what) for version, pattern, what in NEWER_SYNTAX]


class NewerSyntaxError(SyntaxError):
    """A source uses syntax from a newer Python than the one running.

    Parameters
    ----------
    version : tuple of int
        The ``(major, minor)`` release the syntax needs.
    feature : str
        A short name for the syntax, such as ``"'type' alias statement"``.

    Examples
    --------
    >>> str(NewerSyntaxError((3, 12), "type parameter list"))
    'uses a type parameter list, which needs Python 3.12'
    """

    def __init__(self, version: tuple[int, int], feature: str) -> None:
        super().__init__(f"uses a {feature}, which needs Python {version[0]}.{version[1]}")
        self.version = version
        self.feature = feature


def required_python(source: str, running: tuple[int, int] | None = None) -> tuple[tuple[int, int], str] | None:
    """Return the newest release, above *running*, whose syntax *source* appears to use.

    Only meaningful for a source that failed to parse: the patterns are
    heuristics, so a source that parses is never judged by them.

    Parameters
    ----------
    source : str
        The module text.
    running : tuple of int, optional
        The ``(major, minor)`` interpreter version.  Defaults to the running one.

    Returns
    -------
    tuple or None
        ``((major, minor), feature)``, or ``None`` when no newer syntax is found.

    Examples
    --------
    >>> required_python("type Pair[T] = tuple[T, T]", running=(3, 11))
    ((3, 12), "'type' alias statement")
    >>> required_python("x = 1", running=(3, 11)) is None
    True
    """
    running = running or sys.version_info[:2]
    for version, pattern, feature in _PATTERNS:
        if version > running and pattern.search(source):
            return version, feature
    return None
