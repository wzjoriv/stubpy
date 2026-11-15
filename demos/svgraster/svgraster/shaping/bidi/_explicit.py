"""Paragraph level (P2-P3), explicit levels (X1-X8) and isolating run sequences (X10, BD13)."""
from __future__ import annotations

from dataclasses import dataclass

from ._classes import AL, B, BN, EMBEDDINGS, FSI, ISOLATES, L, LRE, LRI, LRO, PDF, PDI, R, REMOVED, RLE, RLI, RLO

MAX_DEPTH = 125


def matching_pdis(types: list[int]) -> dict[int, int]:
    """Isolate initiator index to its matching PDI index (BD9)."""
    out, stack = {}, []
    for i, t in enumerate(types):
        if t in ISOLATES:
            stack.append(i)
        elif t == PDI and stack:
            out[stack.pop()] = i
        elif t == B:
            stack.clear()
    return out


def first_strong(types: list[int], start: int, end: int, pdis: dict[int, int]) -> int | None:
    """0 or 1 for the first L or R/AL in ``types[start:end]`` outside isolates (P2)."""
    i = start
    while i < end:
        t = types[i]
        if t == L:
            return 0
        if t in (R, AL):
            return 1
        if t in ISOLATES:
            i = pdis.get(i, end)
        elif t == B:
            return None
        i += 1
    return None


@dataclass
class _Entry:
    level: int
    override: int | None
    isolate: bool


def _next_level(level: int, odd: bool) -> int:
    return (level + 1) | 1 if odd else (level + 2) & ~1


def explicit_levels(types: list[int], para: int, pdis: dict[int, int]) -> list[int]:
    """Apply X1-X8; overrides rewrite ``types`` in place."""
    n = len(types)
    levels = [para] * n
    stack = [_Entry(para, None, False)]
    over_iso = over_emb = valid_iso = 0
    for i in range(n):
        t, top = types[i], stack[-1]
        if t in EMBEDDINGS:
            new = _next_level(top.level, t in (RLE, RLO))
            levels[i] = top.level
            if new <= MAX_DEPTH and not over_iso and not over_emb:
                stack.append(_Entry(new, R if t == RLO else L if t == LRO else None, False))
            elif not over_iso:
                over_emb += 1
        elif t in ISOLATES:
            levels[i] = top.level
            if top.override is not None:
                types[i] = top.override
            rtl = t == RLI or (t == FSI and first_strong(types, i + 1, pdis.get(i, n), pdis) == 1)
            new = _next_level(top.level, rtl)
            if new <= MAX_DEPTH and not over_iso and not over_emb:
                valid_iso += 1
                stack.append(_Entry(new, None, True))
            else:
                over_iso += 1
        elif t == PDI:
            if over_iso:
                over_iso -= 1
            elif valid_iso:
                over_emb = 0
                while not stack[-1].isolate:
                    stack.pop()
                stack.pop()
                valid_iso -= 1
            top = stack[-1]
            levels[i] = top.level
            if top.override is not None:
                types[i] = top.override
        elif t == PDF:
            levels[i] = top.level
            if over_iso:
                pass
            elif over_emb:
                over_emb -= 1
            elif not top.isolate and len(stack) >= 2:
                stack.pop()
        elif t == B:
            levels[i] = para
        else:
            levels[i] = top.level
            if top.override is not None and t != BN:
                types[i] = top.override
    return levels


def run_sequences(types: list[int], levels: list[int], pdis: dict[int, int]) -> list[list[int]]:
    """Isolating run sequences as index lists, removed characters skipped (X9, X10)."""
    kept = [i for i, t in enumerate(types) if t not in REMOVED]
    runs: list[list[int]] = []
    for i in kept:
        if runs and levels[runs[-1][-1]] == levels[i]:
            runs[-1].append(i)
        else:
            runs.append([i])
    by_start = {run[0]: run for run in runs}
    pdi_targets = set(pdis.values())
    sequences = []
    for run in runs:
        if types[run[0]] == PDI and run[0] in pdi_targets:
            continue
        seq = list(run)
        while types[seq[-1]] in ISOLATES and seq[-1] in pdis and pdis[seq[-1]] in by_start:
            seq.extend(by_start[pdis[seq[-1]]])
        sequences.append(seq)
    return sequences
