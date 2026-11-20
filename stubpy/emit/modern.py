"""
Deprecated ``typing`` aliases in stub text rewritten to their modern forms (``List`` to ``list``, ...).
"""
from __future__ import annotations

import io
import tokenize

from stubpy._constants import TYPING_MOVED
from stubpy.analysis.imports import defined_names
from stubpy.emit._constants import TYPING_RENAMES

__all__ = ["modernize"]

_TYPING_MODULES = frozenset({"typing", "typing_extensions"})


def _from_typing(name: str, import_map: dict[str, str], local: set[str]) -> bool:
    """True when the bare *name* in a stub means the ``typing`` alias: not defined here nor imported from elsewhere."""
    if name in local:
        return False
    stmt = import_map.get(name)
    return stmt is None or stmt.split()[1] in _TYPING_MODULES


def modernize(text: str, import_map: dict[str, str] | None = None) -> str:
    """Return stub text with deprecated ``typing`` aliases replaced.

    ``List`` / ``typing.List`` become ``list`` (likewise ``Dict``, ``Set``,
    ``FrozenSet``, ``Tuple``, ``Type``), ``ContextManager`` becomes
    ``AbstractContextManager``, and ``typing.Callable`` / ``typing.Pattern``
    and friends lose their ``typing.`` prefix; the header then imports
    them from ``collections.abc``, ``contextlib``, ``re`` or ``collections``.
    Strings and comments are left alone.

    Parameters
    ----------
    text : str
        The stub text.
    import_map : dict of str to str, optional
        Maps imported names to their import statements, so a name imported
        from elsewhere is not mistaken for the ``typing`` alias. Defaults to None.

    Returns
    -------
    str
        The rewritten text; *text* itself when it cannot be tokenised or nothing changes.

    Examples
    --------
    >>> modernize("def f(x: List[int], cm: typing.ContextManager[str]) -> 'List': ...")
    "def f(x: list[int], cm: AbstractContextManager[str]) -> 'List': ..."
    """
    names = TYPING_RENAMES.keys() | TYPING_MOVED
    if not any(n in text for n in names):
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    local = defined_names(text)
    import_map = import_map or {}
    edits: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string not in names:
            continue
        prev = tokens[i - 1] if i else None
        dotted = prev is not None and prev.string == "." and i >= 2 and tokens[i - 2].string in _TYPING_MODULES
        if prev is not None and prev.string == "." and not dotted:
            continue
        if not dotted and not _from_typing(tok.string, import_map, local):
            continue
        start = tokens[i - 2].start if dotted else tok.start
        edits.append((start, tok.end, TYPING_RENAMES.get(tok.string, tok.string)))
    if not edits:
        return text
    lines = text.splitlines(keepends=True)
    for (srow, scol), (erow, ecol), new in reversed(edits):
        if srow != erow:
            continue
        line = lines[srow - 1]
        lines[srow - 1] = line[:scol] + new + line[ecol:]
    return "".join(lines)
