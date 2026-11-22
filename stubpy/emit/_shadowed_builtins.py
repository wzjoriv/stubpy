"""
Builtin types a class shadows with a member of the same name (``def dict(self)``, ``str: Any``): inside that class,
annotations meaning the builtin are written ``builtins.X``.
"""
from __future__ import annotations

import builtins
import io
import tokenize

_SKIPPED = (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)
_BUILTIN_TYPES = frozenset(n for n in dir(builtins) if isinstance(getattr(builtins, n), type) and not n.startswith("_")
                           and not n[:1].isupper())


def qualify_shadowed_builtins(text: str) -> tuple[str, bool]:
    """Return *text* with builtin types shadowed by a class member written ``builtins.X``, and whether any were.

    Examples
    --------
    >>> print(qualify_shadowed_builtins("class M:\\n    def dict(self) -> dict[str, int]: ...\\n")[0])
    class M:
        def dict(self) -> builtins.dict[str, int]: ...
    <BLANKLINE>
    >>> qualify_shadowed_builtins("def dict() -> dict: ...\\n")[1]
    False
    """
    if not any(f" {n}" in text for n in _BUILTIN_TYPES):
        return text, False
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text, False
    edits: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for start, end in _class_bodies(tokens):
        shadowed = _members(tokens, start, end) & _BUILTIN_TYPES
        if shadowed:
            edits.extend((tokens[i].start, tokens[i].end) for i in range(start, end)
                         if tokens[i].type == tokenize.NAME and tokens[i].string in shadowed and _is_reference(tokens, i))
    if not edits:
        return text, False
    lines = text.splitlines(keepends=True)
    for (row, col), _ in sorted(set(edits), reverse=True):
        line = lines[row - 1]
        lines[row - 1] = f"{line[:col]}builtins.{line[col:]}"
    return "".join(lines), True


def _class_bodies(tokens: list[tokenize.TokenInfo]) -> list[tuple[int, int]]:
    """``(first, past_last)`` token indexes of each class body (its indented block)."""
    bodies = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string != "class" or tok.start[1] != tok.line.find("class"):
            continue
        j = next((k for k in range(i, len(tokens)) if tokens[k].type == tokenize.INDENT), None)
        if j is None or any(tokens[k].type == tokenize.NEWLINE and tokens[k + 1].type != tokenize.INDENT
                            for k in range(i, j) if k + 1 < len(tokens)):
            continue
        depth, k = 0, j
        while k < len(tokens):
            depth += tokens[k].type == tokenize.INDENT
            depth -= tokens[k].type == tokenize.DEDENT
            if depth == 0:
                break
            k += 1
        bodies.append((j, k))
    return bodies


def _members(tokens: list[tokenize.TokenInfo], start: int, end: int) -> set[str]:
    """Names the class body at *start* binds directly: its methods, nested classes and attributes."""
    column = tokens[start].end[1]
    names = set()
    for i in range(start, end):
        tok = tokens[i]
        if tok.type != tokenize.NAME or tok.start[1] != column:
            continue
        if tok.string in ("def", "class", "async") and i + 1 < end:
            target = tokens[i + 2] if tok.string == "async" and i + 2 < end else tokens[i + 1]
            names.add(target.string)
        elif i + 1 < end and tokens[i + 1].string in (":", "="):
            names.add(tok.string)
    return names


def _is_reference(tokens: list[tokenize.TokenInfo], i: int) -> bool:
    """True when the NAME at *i* is read as a type: not a definition, parameter name, attribute or member."""
    before = next((tokens[j] for j in range(i - 1, -1, -1) if tokens[j].type not in _SKIPPED), None)
    after = next((tokens[j] for j in range(i + 1, len(tokens)) if tokens[j].type not in _SKIPPED), None)
    if before is not None and before.string in ("def", "class", "."):
        return False
    if after is not None and after.string in (":", "=") and (
            before is None or before.string in ("(", ",", "*", "**") or before.end[0] < tokens[i].start[0]):
        return False
    if before is None:
        return False
    if before.string in (":", "->", "|"):
        return True
    return before.string in ("[", ",") and _innermost_bracket(tokens, i) == "["


def _innermost_bracket(tokens: list[tokenize.TokenInfo], i: int) -> str | None:
    """The unclosed bracket around token *i* (``[`` in a type, ``(`` in a parameter list), or ``None``."""
    depth = 0
    for j in range(i - 1, -1, -1):
        s = tokens[j].string
        if tokens[j].type != tokenize.OP:
            continue
        if s in ")]}":
            depth += 1
        elif s in "([{":
            if depth == 0:
                return s
            depth -= 1
    return None
