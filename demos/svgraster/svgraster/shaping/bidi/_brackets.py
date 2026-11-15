"""Paired bracket resolution (BD16, N0)."""
from __future__ import annotations

import unicodedata

from .._ucd import BRACKETS
from ._classes import AN, EN, L, NSM, ON, R

MAX_STACK = 63
OPEN = "o"


def _canonical(cp: int) -> int:
    decomposed = unicodedata.normalize("NFD", chr(cp))
    return ord(decomposed) if len(decomposed) == 1 else cp


def bracket_pairs(cps: list[int], types: list[int]) -> list[tuple[int, int]]:
    """Positions of matched bracket pairs, sorted by opener (BD16)."""
    stack: list[tuple[int, int]] = []
    pairs = []
    for i, cp in enumerate(cps):
        info = BRACKETS.get(cp)
        if info is None or types[i] != ON:
            continue
        if info[1] == OPEN:
            if len(stack) == MAX_STACK:
                break
            stack.append((_canonical(info[0]), i))
            continue
        me = _canonical(cp)
        for k in range(len(stack) - 1, -1, -1):
            if stack[k][0] == me:
                pairs.append((stack[k][1], i))
                del stack[k:]
                break
    return sorted(pairs)


def _strong(t: int) -> int | None:
    if t == L:
        return L
    if t in (R, EN, AN):
        return R
    return None


def resolve_brackets(cps: list[int], types: list[int], original: list[int], sos: int, embedding: int) -> None:
    """N0 in place on one isolating run sequence."""
    opposite = R if embedding == L else L
    for open_, close in bracket_pairs(cps, types):
        inside = {_strong(t) for t in types[open_ + 1:close]}
        if embedding in inside:
            fill = embedding
        elif opposite in inside:
            fill = sos
            for t in reversed(types[:open_]):
                found = _strong(t)
                if found is not None:
                    fill = found
                    break
            fill = opposite if fill == opposite else embedding
        else:
            continue
        for pos in (open_, close):
            types[pos] = fill
            k = pos + 1
            while k < len(types) and original[k] == NSM:
                types[k] = fill
                k += 1
