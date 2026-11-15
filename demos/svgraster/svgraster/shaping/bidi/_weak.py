"""Weak (W1-W7), neutral (N1-N2) and implicit (I1-I2) resolution in pure Python.

Each function works on one isolating run sequence: ``types`` are its
current types, ``sos``/``eos`` are ``L`` or ``R``. The compiled
``svgraster._bidi`` module implements the same functions.
"""
from __future__ import annotations

from ._classes import AL, AN, CS, EN, ES, ET, ISOLATES, L, NEUTRAL, NSM, ON, PDI, R


def resolve_weak(types: list[int], sos: int) -> None:
    """W1-W7 in place."""
    n = len(types)
    prev = sos
    for i in range(n):
        if types[i] == NSM:
            types[i] = ON if prev in ISOLATES or prev == PDI else prev
        prev = types[i]
    strong = sos
    for i in range(n):
        t = types[i]
        if t in (L, R, AL):
            strong = t
        elif t == EN and strong == AL:
            types[i] = AN
    for i in range(n):
        if types[i] == AL:
            types[i] = R
    for i in range(1, n - 1):
        t, a, b = types[i], types[i - 1], types[i + 1]
        if t == ES and a == EN and b == EN:
            types[i] = EN
        elif t == CS and a == b and a in (EN, AN):
            types[i] = a
    i = 0
    while i < n:
        if types[i] != ET:
            i += 1
            continue
        j = i
        while j < n and types[j] == ET:
            j += 1
        if (i > 0 and types[i - 1] == EN) or (j < n and types[j] == EN):
            types[i:j] = [EN] * (j - i)
        i = j
    for i in range(n):
        if types[i] in (ES, ET, CS):
            types[i] = ON
    strong = sos
    for i in range(n):
        t = types[i]
        if t in (L, R):
            strong = t
        elif t == EN and strong == L:
            types[i] = L


def _dir(t: int) -> int:
    return L if t == L else R


def resolve_neutral(types: list[int], sos: int, eos: int, embedding: int) -> None:
    """N1-N2 in place; ``embedding`` is ``L`` or ``R``."""
    n = len(types)
    i = 0
    while i < n:
        if types[i] not in NEUTRAL:
            i += 1
            continue
        j = i
        while j < n and types[j] in NEUTRAL:
            j += 1
        before = _dir(types[i - 1]) if i > 0 else sos
        after = _dir(types[j]) if j < n else eos
        fill = before if before == after else embedding
        types[i:j] = [fill] * (j - i)
        i = j


def resolve_implicit(types: list[int], levels: list[int]) -> None:
    """I1-I2 in place on the sequence's levels."""
    for i, t in enumerate(types):
        lv = levels[i]
        if lv & 1:
            if t in (L, EN, AN):
                levels[i] = lv + 1
        elif t == R:
            levels[i] = lv + 1
        elif t in (AN, EN):
            levels[i] = lv + 2
