"""The Unicode Bidirectional Algorithm (UAX #9) for one paragraph.

Usage::

    from svgraster.shaping.bidi import paragraph

    para = paragraph("abc \u05d0\u05d1\u05d2", direction=None)
    para.levels, para.visual_order()
"""
from __future__ import annotations

from dataclasses import dataclass

from ..._backend import native
from .._ucd import MIRRORS
from . import _weak
from ._brackets import resolve_brackets
from ._classes import B, ISOLATES, L, NAMES, R, REMOVED, S, TRAILING, bidi_classes
from ._explicit import explicit_levels, first_strong, matching_pdis, run_sequences

LTR, RTL = 0, 1


@dataclass
class Paragraph:
    """Resolved embedding levels of a paragraph."""

    text: str
    level: int
    levels: list[int]
    types: list[int]

    @property
    def removed(self) -> list[bool]:
        """Characters removed by rule X9 (embedding controls and boundary neutrals)."""
        return [t in REMOVED for t in self.types]

    def line_levels(self, start: int = 0, end: int | None = None) -> list[int]:
        """Levels of ``text[start:end]`` after rule L1."""
        end = len(self.text) if end is None else end
        levels = self.levels[start:end]
        types = self.types[start:end]
        trailing = True
        for i in range(len(levels) - 1, -1, -1):
            t = types[i]
            if t in (S, B):
                levels[i] = self.level
                trailing = True
            elif trailing and t in TRAILING:
                levels[i] = self.level
            else:
                trailing = False
        return levels

    def visual_order(self, start: int = 0, end: int | None = None) -> list[int]:
        """Logical indices of ``text[start:end]`` in display order (L1-L2)."""
        return [start + i for i in reorder(self.line_levels(start, end))]

    def mirror(self, i: int) -> str:
        """Character ``i``, replaced by its mirror when it is at an odd level (L4)."""
        ch = self.text[i]
        if self.levels[i] & 1:
            return chr(MIRRORS.get(ord(ch), ord(ch)))
        return ch


def reorder(levels: list[int]) -> list[int]:
    """Indices in display order for a line of resolved levels (L2)."""
    order = list(range(len(levels)))
    if not levels:
        return order
    high = max(levels)
    low = min(lv for lv in levels if lv & 1) if any(lv & 1 for lv in levels) else high + 1
    for level in range(high, low - 1, -1):
        i, n = 0, len(levels)
        while i < n:
            if levels[order[i]] < level:
                i += 1
                continue
            j = i
            while j < n and levels[order[j]] >= level:
                j += 1
            order[i:j] = order[i:j][::-1]
            i = j
    return order


def _engine():
    mod = native("bidi")
    return mod if mod is not None else _weak


def paragraph(text: str, direction: int | None = None) -> Paragraph:
    """Resolve ``text`` as one paragraph; ``direction`` is ``LTR``, ``RTL`` or ``None`` (P2-P3)."""
    original = bidi_classes(text)
    types = list(original)
    pdis = matching_pdis(types)
    if direction is None:
        direction = first_strong(types, 0, len(types), pdis) or LTR
    levels = explicit_levels(types, direction, pdis)
    cps = [ord(c) for c in text]
    engine = _engine()
    explicit = list(levels)
    for seq in run_sequences(original, explicit, pdis):
        _resolve_sequence(seq, types, original, explicit, levels, cps, direction, engine)
    for i, t in enumerate(original):
        if t in REMOVED:
            levels[i] = levels[i - 1] if i else direction
    return Paragraph(text, direction, levels, original)


def _resolve_sequence(seq, types, original, explicit, levels, cps, para, engine) -> None:
    level = explicit[seq[0]]
    before = _neighbour(seq[0], -1, original, explicit, para)
    last = seq[-1]
    after = para if original[last] in ISOLATES else _neighbour(last, 1, original, explicit, para)
    sos = R if max(level, before) & 1 else L
    eos = R if max(explicit[last], after) & 1 else L
    embedding = R if level & 1 else L
    st = [types[i] for i in seq]
    engine.resolve_weak(st, sos)
    resolve_brackets([cps[i] for i in seq], st, [original[i] for i in seq], sos, embedding)
    engine.resolve_neutral(st, sos, eos, embedding)
    lv = [levels[i] for i in seq]
    engine.resolve_implicit(st, lv)
    for k, i in enumerate(seq):
        types[i] = st[k]
        levels[i] = lv[k]


def _neighbour(i: int, step: int, original, levels, para) -> int:
    i += step
    while 0 <= i < len(original):
        if original[i] not in REMOVED:
            return levels[i]
        i += step
    return para


__all__ = ["LTR", "NAMES", "RTL", "Paragraph", "paragraph", "reorder"]
