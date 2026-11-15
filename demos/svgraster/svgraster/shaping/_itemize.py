"""Script itemization: the Unicode script of each character, with Common and Inherited resolved."""
from __future__ import annotations

import bisect

from ._ucd import SCRIPT_RANGES

COMMON = "Common"
INHERITED = "Inherited"
UNKNOWN = "Unknown"
WEAK = frozenset({COMMON, INHERITED, UNKNOWN})
_STARTS = [r[0] for r in SCRIPT_RANGES]


def script_of(cp: int) -> str:
    """The Unicode Script property of ``cp``."""
    i = bisect.bisect_right(_STARTS, cp) - 1
    if i >= 0 and cp <= SCRIPT_RANGES[i][1]:
        return SCRIPT_RANGES[i][2]
    return UNKNOWN


def scripts(text: str) -> list[str]:
    """The resolved script of each character: weak characters take their neighbour's script."""
    raw = [script_of(ord(ch)) for ch in text]
    out = list(raw)
    current = next((s for s in raw if s not in WEAK), COMMON)
    for i, s in enumerate(raw):
        if s in WEAK:
            out[i] = current
        else:
            current = s
    return out
