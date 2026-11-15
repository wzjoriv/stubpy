"""Version blocks in a stub: the ``if sys.version_info ...`` / ``elif`` / ``else`` around each branch's stubs."""
from __future__ import annotations

import textwrap
from typing import NamedTuple

from stubpy.analysis.harvest.models import Branch, VersionBlock

__all__ = ["Unit", "join_sections", "weave"]


class Unit(NamedTuple):
    """One emitted stub: its text, whether it is a one-line declaration, and its version branch."""
    text: str
    compact: bool
    branch: Branch = ()


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


def weave(units: list[Unit]) -> list[tuple[str, bool]]:
    """Return ``(text, compact)`` sections: unconditional units as they are, each run of one block as its ``if`` chain.

    Units must be in source order, so the members of a block are adjacent.

    Examples
    --------
    >>> block = VersionBlock(1, ["sys.version_info >= (3, 12)", None])
    >>> print(join_sections(weave([Unit("X: int", True, ((block, 0),)), Unit("X: str", True, ((block, 1),))])))
    if sys.version_info >= (3, 12):
        X: int
    else:
        X: str
    """
    out: list[tuple[str, bool]] = []
    i = 0
    while i < len(units):
        if not units[i].branch:
            out.append((units[i].text, units[i].compact))
            i += 1
            continue
        block = units[i].branch[0][0]
        j = i
        while j < len(units) and units[j].branch and units[j].branch[0][0] is block:
            j += 1
        out.append((_block_text(block, units[i:j]), False))
        i = j
    return out


def _block_text(block: VersionBlock, units: list[Unit]) -> str:
    """Return the ``if`` / ``elif`` / ``else`` text of *block*; trailing branches without stubs are left out."""
    members: dict[int, list[Unit]] = {}
    for unit in units:
        members.setdefault(unit.branch[0][1], []).append(Unit(unit.text, unit.compact, unit.branch[1:]))
    parts: list[str] = []
    for index, test in enumerate(block.tests[:max(members) + 1]):
        head = "else:" if test is None else f"if {test}:" if index == 0 else f"elif {test}:"
        body = join_sections(weave(members.get(index, []))) or "..."
        parts.append(f"{head}\n{textwrap.indent(body, '    ')}")
    return "\n".join(parts)
