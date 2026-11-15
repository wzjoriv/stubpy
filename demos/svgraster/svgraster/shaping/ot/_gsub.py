"""GSUB subtables: single, multiple, alternate, ligature, contexts, extension and reverse chaining."""
from __future__ import annotations

import struct

from ._context import ContextSubtable
from ._tables import GLYPH_MARK, Coverage, offsets, u16, u16s

SINGLE, MULTIPLE, ALTERNATE, LIGATURE, CONTEXT, CHAIN, EXTENSION, REVERSE = range(1, 9)
GLYPH_MASK = 0xFFFF


class SingleSubst:
    """Type 1: a delta (format 1) or a substitute array (format 2)."""

    def __init__(self, data: bytes, pos: int):
        self.coverage = Coverage(data, pos + u16(data, pos + 2))
        if u16(data, pos) == 1:
            self.delta, self.subs = u16(data, pos + 4), None
        else:
            self.delta, self.subs = 0, u16s(data, pos + 6, u16(data, pos + 4))

    def substitute(self, gid: int) -> int | None:
        """The substitute for ``gid``, if covered."""
        k = self.coverage(gid)
        if k is None:
            return None
        if self.subs is None:
            return (gid + self.delta) & GLYPH_MASK
        return self.subs[k] if k < len(self.subs) else None

    def apply(self, ctx, i: int) -> int | None:
        new = self.substitute(ctx.buf[i].gid)
        if new is None:
            return None
        ctx.buf[i].gid = new
        ctx.classify(ctx.buf[i])
        return i + 1


class _Sequences:
    def __init__(self, data: bytes, pos: int):
        self.coverage = Coverage(data, pos + u16(data, pos + 2))
        self.items = [u16s(data, o + 2, u16(data, o)) for o in offsets(data, pos, pos + 6, u16(data, pos + 4))]

    def get(self, gid: int):
        k = self.coverage(gid)
        return self.items[k] if k is not None and k < len(self.items) else None


class MultipleSubst(_Sequences):
    """Type 2: one glyph into a sequence."""

    def apply(self, ctx, i: int) -> int | None:
        seq = self.get(ctx.buf[i].gid)
        if seq is None:
            return None
        old = ctx.buf[i]
        new = [old.copy(g) for g in seq]
        for info in new:
            ctx.classify(info)
        ctx.buf[i:i + 1] = new
        return i + len(new)


class AlternateSubst(_Sequences):
    """Type 3: the first alternate (feature value 1)."""

    def apply(self, ctx, i: int) -> int | None:
        alts = self.get(ctx.buf[i].gid)
        if not alts:
            return None
        ctx.buf[i].gid = alts[0]
        ctx.classify(ctx.buf[i])
        return i + 1


def _same(value: int, gid: int) -> bool:
    return gid == value


def _covered(value: Coverage, gid: int) -> bool:
    return gid in value


class LigatureSubst:
    """Type 4: component sequences into ligature glyphs."""

    def __init__(self, data: bytes, pos: int):
        self.coverage = Coverage(data, pos + u16(data, pos + 2))
        self.sets = []
        for set_pos in offsets(data, pos, pos + 6, u16(data, pos + 4)):
            ligs = []
            for lp in offsets(data, set_pos, set_pos + 2, u16(data, set_pos)):
                count = u16(data, lp + 2)
                ligs.append((u16(data, lp), u16s(data, lp + 4, count - 1)))
            self.sets.append(ligs)

    def apply(self, ctx, i: int) -> int | None:
        k = self.coverage(ctx.buf[i].gid)
        if k is None or k >= len(self.sets):
            return None
        for lig, components in self.sets[k]:
            found = ctx.match(i, 1, components, _same, True)
            if found is not None:
                ligate(ctx, [i, *found], lig)
                return i + 1
        return None


def ligate(ctx, positions: list[int], lig: int) -> None:
    """Replace the glyphs at ``positions`` by ``lig``; skipped marks between them join the ligature."""
    buf = ctx.buf
    first = buf[positions[0]]
    marks_only = all(buf[p].gclass == GLYPH_MARK for p in positions)
    lig_id = 0 if marks_only else ctx.new_lig_id()
    first.gid = lig
    first.cluster = min(buf[p].cluster for p in positions)
    first.lig_id, first.lig_comp, first.lig_comps = lig_id, 0, len(positions)
    ctx.classify(first, ligature=not marks_only)
    if lig_id:
        for k in range(1, len(positions)):
            for j in range(positions[k - 1] + 1, positions[k]):
                buf[j].lig_id, buf[j].lig_comp = lig_id, k
    for p in reversed(positions[1:]):
        del buf[p]


class ReverseChainSingle:
    """Type 8: single substitution matched from the end, with coverage context."""

    def __init__(self, data: bytes, pos: int):
        self.coverage = Coverage(data, pos + u16(data, pos + 2))
        p = pos + 4
        groups = []
        for _ in range(2):
            n = u16(data, p)
            groups.append(tuple(Coverage(data, o) for o in offsets(data, pos, p + 2, n)))
            p += 2 + 2 * n
        self.backtrack, self.lookahead = groups
        self.subs = u16s(data, p + 2, u16(data, p))

    def apply(self, ctx, i: int) -> int | None:
        k = self.coverage(ctx.buf[i].gid)
        if k is None or k >= len(self.subs):
            return None
        if self.backtrack and ctx.match(i, -1, self.backtrack, _covered, False) is None:
            return None
        if self.lookahead and ctx.match(i, 1, self.lookahead, _covered, False) is None:
            return None
        ctx.buf[i].gid = self.subs[k]
        ctx.classify(ctx.buf[i])
        return i


_TYPES = {SINGLE: SingleSubst, MULTIPLE: MultipleSubst, ALTERNATE: AlternateSubst, LIGATURE: LigatureSubst,
          REVERSE: ReverseChainSingle}


def parse_gsub(kind: int, data: bytes, pos: int):
    """A subtable object for GSUB lookup ``kind`` at ``pos`` (``None`` when unsupported)."""
    try:
        if kind in (CONTEXT, CHAIN):
            return ContextSubtable(data, pos, kind == CHAIN)
        cls = _TYPES.get(kind)
        return cls(data, pos) if cls is not None else None
    except (IndexError, ValueError, struct.error):
        return None
