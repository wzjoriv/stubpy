"""The glyph buffer and the lookup driver shared by GSUB and GPOS."""
from __future__ import annotations

import unicodedata
from collections.abc import Callable

from ._tables import GLYPH_BASE, GLYPH_LIGATURE, GLYPH_MARK, Gdef, LayoutTable

IGNORE_BASE = 0x0002
IGNORE_LIGATURES = 0x0004
IGNORE_MARKS = 0x0008
USE_MARK_FILTERING_SET = 0x0010
MARK_ATTACHMENT_TYPE = 0xFF00
ALL_MASKS = -1
MARK_CATEGORIES = frozenset({"Mn", "Me"})
ATTACH_MARK, ATTACH_CURSIVE = 1, 2


class Info:
    """One glyph of the buffer with its source character and position."""

    __slots__ = ("gid", "cp", "cluster", "mask", "gclass", "lig_id", "lig_comp", "lig_comps",
                 "x_adv", "y_adv", "x_off", "y_off", "attach", "attach_kind", "cat", "pos", "syllable")

    def __init__(self, gid: int, cp: int, cluster: int, mask: int = 0):
        self.gid, self.cp, self.cluster, self.mask = gid, cp, cluster, mask
        self.gclass = GLYPH_BASE
        self.lig_id = self.lig_comp = 0
        self.lig_comps = 1
        self.x_adv = self.y_adv = self.x_off = self.y_off = 0
        self.attach = -1
        self.attach_kind = 0
        self.cat = self.pos = self.syllable = 0

    def copy(self, gid: int) -> Info:
        """A copy carrying ``gid``."""
        out = Info(gid, self.cp, self.cluster, self.mask)
        for name in ("gclass", "lig_id", "lig_comp", "cat", "pos", "syllable"):
            setattr(out, name, getattr(self, name))
        return out

    def __repr__(self) -> str:
        return f"Info(gid={self.gid}, cp=U+{self.cp:04X}, cluster={self.cluster})"


def synthetic_class(cp: int) -> int:
    """A GDEF-like class for fonts without GDEF: marks from the Unicode category."""
    return GLYPH_MARK if unicodedata.category(chr(cp)) in MARK_CATEGORIES else GLYPH_BASE


class Applier:
    """Applies lookups of one table to a buffer (``rtl`` is the run direction)."""

    def __init__(self, table: LayoutTable, gdef: Gdef, buf: list[Info], parse: Callable, rtl: bool = False):
        self.table, self.gdef, self.buf, self._parse, self.rtl = table, gdef, buf, parse, rtl
        self.flag = 0
        self.mark_set = -1
        self.mask = ALL_MASKS
        self._lig_ids = 0

    def classify(self, info: Info, ligature: bool = False) -> None:
        """Refresh ``info.gclass`` after a substitution."""
        cls = self.gdef.glyph_class(info.gid) if self.gdef.present else 0
        info.gclass = cls or (GLYPH_LIGATURE if ligature else info.gclass)

    def new_lig_id(self) -> int:
        """A fresh ligature id for mark-to-ligature bookkeeping."""
        self._lig_ids = self._lig_ids % 255 + 1
        return self._lig_ids

    def skip(self, info: Info) -> bool:
        """Whether the current lookup flag ignores ``info``."""
        cls, flag = info.gclass, self.flag
        if cls == GLYPH_MARK:
            if flag & IGNORE_MARKS:
                return True
            if flag & USE_MARK_FILTERING_SET:
                return not self.gdef.in_mark_set(self.mark_set, info.gid)
            if flag & MARK_ATTACHMENT_TYPE:
                return self.gdef.mark_class(info.gid) != flag >> 8
            return False
        if cls == GLYPH_LIGATURE:
            return bool(flag & IGNORE_LIGATURES)
        return cls == GLYPH_BASE and bool(flag & IGNORE_BASE)

    def next(self, i: int, step: int) -> int | None:
        """The next index from ``i`` in direction ``step`` that is not skipped."""
        buf, j = self.buf, i + step
        while 0 <= j < len(buf):
            if not self.skip(buf[j]):
                return j
            j += step
        return None

    def match(self, i: int, step: int, values, test: Callable, need_mask: bool) -> list[int] | None:
        """Indices of ``len(values)`` glyphs after (or before) ``i`` that satisfy ``test(value, gid)``."""
        out, j = [], i
        for value in values:
            j = self.next(j, step)
            if j is None:
                return None
            info = self.buf[j]
            if (need_mask and not info.mask & self.mask) or not test(value, info.gid):
                return None
            out.append(j)
        return out

    def subtables(self, index: int) -> list:
        """Parsed subtables of lookup ``index``."""
        lookup = self.table.lookup(index)
        if lookup.parsed is None:
            parsed = [self._parse(lookup.kind, self.table.data, pos) for pos in lookup.subtables]
            lookup.parsed = [p for p in parsed if p is not None]
        return lookup.parsed

    def _use(self, index: int) -> tuple:
        saved = (self.flag, self.mark_set)
        lookup = self.table.lookup(index)
        self.flag, self.mark_set = lookup.flag, lookup.mark_set
        return saved

    def run(self, index: int, mask: int, reverse: bool = False) -> None:
        """Apply lookup ``index`` across the buffer to glyphs carrying ``mask``."""
        subs = self.subtables(index)
        if not subs:
            return
        saved = self._use(index)
        self.mask = mask
        buf = self.buf
        i = len(buf) - 1 if reverse else 0
        while 0 <= i < len(buf):
            info = buf[i]
            done = None
            if info.mask & mask and not self.skip(info):
                for sub in subs:
                    done = sub.apply(self, i)
                    if done is not None:
                        break
            if reverse:
                i -= 1
            else:
                i = done if done is not None and done > i else i + 1
        self.flag, self.mark_set = saved

    def apply_at(self, index: int, i: int) -> bool:
        """Apply nested lookup ``index`` at position ``i`` (for contextual lookups)."""
        if not 0 <= i < len(self.buf) or index >= len(self.table):
            return False
        saved = self._use(index)
        try:
            if self.skip(self.buf[i]):
                return False
            return any(sub.apply(self, i) is not None for sub in self.subtables(index))
        finally:
            self.flag, self.mark_set = saved

    def apply_records(self, positions: list[int], records) -> int:
        """Run the nested ``(sequence index, lookup)`` records; the index after the match."""
        end = positions[-1] + 1
        for seq, index in records:
            if seq >= len(positions):
                continue
            before = len(self.buf)
            self.apply_at(index, positions[seq])
            delta = len(self.buf) - before
            if delta:
                end += delta
                floor = positions[seq]
                for k in range(seq + 1, len(positions)):
                    positions[k] = min(max(floor, positions[k] + delta), len(self.buf) - 1)
        return max(end, positions[0] + 1)
