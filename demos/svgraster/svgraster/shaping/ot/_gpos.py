"""GPOS subtables: single, pair, cursive, mark-to-base/ligature/mark, contexts and extension."""
from __future__ import annotations

import struct

from ._context import ContextSubtable
from ._engine import ATTACH_CURSIVE, ATTACH_MARK
from ._tables import GLYPH_MARK, ClassDef, Coverage, i16, offsets, u16, u16s

SINGLE, PAIR, CURSIVE, MARK_BASE, MARK_LIG, MARK_MARK, CONTEXT, CHAIN = range(1, 9)
RIGHT_TO_LEFT = 0x0001
VALUE_BITS = 8
POSITION_BITS = 4
ZERO = (0, 0, 0, 0)


def value_size(fmt: int) -> int:
    """Bytes in a value record of format ``fmt``."""
    return 2 * bin(fmt & 0xFF).count("1")


def read_value(data: bytes, pos: int, fmt: int) -> tuple[int, int, int, int]:
    """``(x placement, y placement, x advance, y advance)``; device tables are ignored."""
    out = [0, 0, 0, 0]
    for bit in range(POSITION_BITS):
        if fmt & (1 << bit):
            out[bit] = i16(data, pos)
            pos += 2
    return tuple(out)


def adjust(info, value) -> None:
    """Add a value record to a glyph's position."""
    info.x_off += value[0]
    info.y_off += value[1]
    info.x_adv += value[2]
    info.y_adv += value[3]


def read_anchor(data: bytes, pos: int) -> tuple[int, int]:
    """An anchor's ``(x, y)`` (formats 1-3)."""
    return i16(data, pos + 2), i16(data, pos + 4)


class SinglePos:
    """Type 1: one value for every covered glyph, or one per glyph."""

    def __init__(self, data: bytes, pos: int):
        fmt, cov, vf = u16s(data, pos, 3)
        self.coverage = Coverage(data, pos + cov)
        if fmt == 1:
            self.values = [read_value(data, pos + 6, vf)]
        else:
            size = value_size(vf)
            self.values = [read_value(data, pos + 8 + k * size, vf) for k in range(u16(data, pos + 6))]

    def apply(self, ctx, i: int) -> int | None:
        k = self.coverage(ctx.buf[i].gid)
        if k is None:
            return None
        adjust(ctx.buf[i], self.values[min(k, len(self.values) - 1)])
        return i + 1


class PairPos:
    """Type 2: glyph pairs (format 1) or class pairs (format 2)."""

    def __init__(self, data: bytes, pos: int):
        self.data = data
        fmt, cov, self.vf1, self.vf2 = u16s(data, pos, 4)
        self.fmt = fmt
        self.coverage = Coverage(data, pos + cov)
        self.size1, self.size2 = value_size(self.vf1), value_size(self.vf2)
        if fmt == 1:
            self.sets = offsets(data, pos, pos + 10, u16(data, pos + 8))
        else:
            c1, c2, self.n1, self.n2 = u16s(data, pos + 8, 4)
            self.class1, self.class2 = ClassDef(data, pos + c1), ClassDef(data, pos + c2)
            self.records = pos + 16

    def _values(self, k: int, left: int, right: int) -> int | None:
        rec = self.size1 + self.size2
        if self.fmt == 1:
            if k >= len(self.sets):
                return None
            sp = self.sets[k]
            lo, hi = 0, u16(self.data, sp)
            while lo < hi:
                mid = (lo + hi) // 2
                at = sp + 2 + mid * (2 + rec)
                g = u16(self.data, at)
                if g == right:
                    return at + 2
                lo, hi = (mid + 1, hi) if g < right else (lo, mid)
            return None
        c1, c2 = self.class1(left), self.class2(right)
        if c1 >= self.n1 or c2 >= self.n2:
            return None
        return self.records + (c1 * self.n2 + c2) * rec

    def apply(self, ctx, i: int) -> int | None:
        left = ctx.buf[i]
        k = self.coverage(left.gid)
        if k is None:
            return None
        j = ctx.next(i, 1)
        if j is None or not ctx.buf[j].mask & ctx.mask:
            return None
        at = self._values(k, left.gid, ctx.buf[j].gid)
        if at is None:
            return None
        adjust(left, read_value(self.data, at, self.vf1))
        if self.vf2:
            adjust(ctx.buf[j], read_value(self.data, at + self.size1, self.vf2))
            return j + 1
        return j


class CursivePos:
    """Type 3: entry and exit anchors joining consecutive glyphs."""

    def __init__(self, data: bytes, pos: int):
        self.coverage = Coverage(data, pos + u16(data, pos + 2))
        self.records = []
        for k in range(u16(data, pos + 4)):
            entry, exit_ = u16s(data, pos + 6 + 4 * k, 2)
            self.records.append((read_anchor(data, pos + entry) if entry else None,
                                 read_anchor(data, pos + exit_) if exit_ else None))

    def _record(self, gid: int):
        k = self.coverage(gid)
        return self.records[k] if k is not None and k < len(self.records) else (None, None)

    def apply(self, ctx, j: int) -> int | None:
        entry = self._record(ctx.buf[j].gid)[0]
        if entry is None:
            return None
        i = ctx.next(j, -1)
        if i is None:
            return None
        exit_ = self._record(ctx.buf[i].gid)[1]
        if exit_ is None:
            return None
        prev, cur = ctx.buf[i], ctx.buf[j]
        if ctx.rtl:
            d = exit_[0] + prev.x_off
            prev.x_adv -= d
            prev.x_off -= d
            cur.x_adv = entry[0] + cur.x_off
        else:
            prev.x_adv = exit_[0] + prev.x_off
            d = entry[0] + cur.x_off
            cur.x_adv -= d
            cur.x_off -= d
        child, parent, dy = (i, j, entry[1] - exit_[1]) if ctx.flag & RIGHT_TO_LEFT else (j, i, exit_[1] - entry[1])
        ctx.buf[child].y_off = dy
        ctx.buf[child].attach, ctx.buf[child].attach_kind = parent, ATTACH_CURSIVE
        return j + 1


class _MarkAttach:
    def __init__(self, data: bytes, pos: int, ligature: bool = False):
        fmt, mcov, bcov, self.classes, marks, bases = u16s(data, pos, 6)
        self.mark_cov = Coverage(data, pos + mcov)
        self.base_cov = Coverage(data, pos + bcov)
        ma = pos + marks
        self.marks = []
        for k in range(u16(data, ma)):
            cls, off = u16s(data, ma + 2 + 4 * k, 2)
            self.marks.append((cls, read_anchor(data, ma + off)))
        ba = pos + bases
        if ligature:
            self.bases = [self._matrix(data, la) for la in offsets(data, ba, ba + 2, u16(data, ba))]
        else:
            self.bases = self._matrix(data, ba)

    def _matrix(self, data: bytes, at: int) -> list[list]:
        rows = []
        for r in range(u16(data, at)):
            offs = u16s(data, at + 2 + 2 * r * self.classes, self.classes)
            rows.append([read_anchor(data, at + o) if o else None for o in offs])
        return rows

    def _attach(self, ctx, i: int, j: int, anchor) -> int | None:
        k = self.mark_cov(ctx.buf[i].gid)
        cls, mark_anchor = self.marks[k]
        if anchor is None or cls >= len(anchor) or anchor[cls] is None:
            return None
        base_anchor = anchor[cls]
        mark = ctx.buf[i]
        mark.x_off = base_anchor[0] - mark_anchor[0]
        mark.y_off = base_anchor[1] - mark_anchor[1]
        mark.attach, mark.attach_kind = j, ATTACH_MARK
        return i + 1

    def _base_before(self, ctx, i: int) -> int | None:
        j = i - 1
        while j >= 0 and ctx.buf[j].gclass == GLYPH_MARK:
            j -= 1
        return j if j >= 0 else None


class MarkBasePos(_MarkAttach):
    """Type 4: marks on the preceding base glyph."""

    def apply(self, ctx, i: int) -> int | None:
        if self.mark_cov(ctx.buf[i].gid) is None:
            return None
        j = self._base_before(ctx, i)
        b = None if j is None else self.base_cov(ctx.buf[j].gid)
        if b is None or b >= len(self.bases):
            return None
        return self._attach(ctx, i, j, self.bases[b])


class MarkLigPos(_MarkAttach):
    """Type 5: marks on a component of the preceding ligature."""

    def __init__(self, data: bytes, pos: int):
        super().__init__(data, pos, ligature=True)

    def apply(self, ctx, i: int) -> int | None:
        if self.mark_cov(ctx.buf[i].gid) is None:
            return None
        j = self._base_before(ctx, i)
        b = None if j is None else self.base_cov(ctx.buf[j].gid)
        if b is None or b >= len(self.bases) or not self.bases[b]:
            return None
        comps = self.bases[b]
        mark, lig = ctx.buf[i], ctx.buf[j]
        if lig.lig_id and mark.lig_id == lig.lig_id and mark.lig_comp:
            comp = min(len(comps), mark.lig_comp) - 1
        else:
            comp = len(comps) - 1
        return self._attach(ctx, i, j, comps[comp])


class MarkMarkPos(_MarkAttach):
    """Type 6: marks on the preceding mark."""

    def apply(self, ctx, i: int) -> int | None:
        if self.mark_cov(ctx.buf[i].gid) is None:
            return None
        j = ctx.next(i, -1)
        if j is None or ctx.buf[j].gclass != GLYPH_MARK:
            return None
        a, b = ctx.buf[i], ctx.buf[j]
        if a.lig_id == b.lig_id:
            ok = a.lig_id == 0 or a.lig_comp == b.lig_comp
        else:
            ok = (a.lig_id > 0 and not a.lig_comp) or (b.lig_id > 0 and not b.lig_comp)
        k = self.base_cov(b.gid)
        if not ok or k is None or k >= len(self.bases):
            return None
        return self._attach(ctx, i, j, self.bases[k])


_TYPES = {SINGLE: SinglePos, PAIR: PairPos, CURSIVE: CursivePos, MARK_BASE: MarkBasePos,
          MARK_LIG: MarkLigPos, MARK_MARK: MarkMarkPos}


def parse_gpos(kind: int, data: bytes, pos: int):
    """A subtable object for GPOS lookup ``kind`` at ``pos`` (``None`` when unsupported)."""
    try:
        if kind in (CONTEXT, CHAIN):
            return ContextSubtable(data, pos, kind == CHAIN)
        cls = _TYPES.get(kind)
        return cls(data, pos) if cls is not None else None
    except (IndexError, ValueError, struct.error):
        return None
