"""Joining emitted symbol stubs into a stub body."""
from __future__ import annotations


def join_sections(tagged: list[tuple[str, bool]]) -> str:
    """Join ``(stub, is_compact)`` pairs: one newline between compact stubs, a blank line otherwise.

    Examples
    --------
    >>> join_sections([("X: int", True), ("Y: str", True), ("def f(): ...", False)])
    'X: int\\nY: str\\n\\ndef f(): ...'
    """
    if not tagged:
        return ""
    parts = [tagged[0][0]]
    for (_, prev_compact), (text, curr_compact) in zip(tagged, tagged[1:], strict=False):
        sep = "\n" if (prev_compact and curr_compact) else "\n\n"
        parts.append(sep + text)
    return "".join(parts)
