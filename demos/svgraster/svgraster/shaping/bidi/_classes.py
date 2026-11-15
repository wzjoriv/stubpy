"""Bidirectional character types as small integers."""
from __future__ import annotations

import unicodedata

NAMES = ("L", "R", "AL", "EN", "ES", "ET", "AN", "CS", "NSM", "BN", "B", "S", "WS", "ON",
         "LRE", "LRO", "RLE", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI")
(L, R, AL, EN, ES, ET, AN, CS, NSM, BN, B, S, WS, ON,
 LRE, LRO, RLE, RLO, PDF, LRI, RLI, FSI, PDI) = range(len(NAMES))
CODES = {name: i for i, name in enumerate(NAMES)}
STRONG = frozenset({L, R, AL})
EMBEDDINGS = frozenset({LRE, LRO, RLE, RLO})
ISOLATES = frozenset({LRI, RLI, FSI})
REMOVED = frozenset({LRE, LRO, RLE, RLO, PDF, BN})
NEUTRAL = frozenset({B, S, WS, ON, LRI, RLI, FSI, PDI})
TRAILING = frozenset({WS, LRI, RLI, FSI, PDI}) | REMOVED


def bidi_class(ch: str) -> int:
    """The bidi type of one character (``L`` when unassigned)."""
    return CODES.get(unicodedata.bidirectional(ch), L)


def bidi_classes(text: str) -> list[int]:
    """The bidi type of each character of ``text``."""
    return [bidi_class(ch) for ch in text]
