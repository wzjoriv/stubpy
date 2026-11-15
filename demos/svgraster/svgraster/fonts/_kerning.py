"""Pair kerning from the ``kern`` table (format 0) and ``GPOS`` (lookup type 2)."""
from __future__ import annotations

import bisect

from ._reader import Reader

KERN_FEATURE = b"kern"
PAIR_ADJUSTMENT = 2
EXTENSION = 9
X_PLACEMENT = 0x0001
X_ADVANCE = 0x0004
KERN_HORIZONTAL = 0x0001
KERN_CROSS_STREAM = 0x0004
KERN_FORMAT0 = 0


def _coverage(data: bytes, pos: int):
    r = Reader(data, pos)
    fmt = r.u16()
    if fmt == 1:
        glyphs = r.array("H", r.u16())
        index = {g: i for i, g in enumerate(glyphs)}
        return index.get
    ranges = [r.array("H", 3) for _ in range(r.u16())]
    starts = [s for s, _, _ in ranges]

    def lookup(gid):
        i = bisect.bisect_right(starts, gid) - 1
        if i >= 0 and gid <= ranges[i][1]:
            return ranges[i][2] + gid - ranges[i][0]
        return None

    return lookup


def _class_def(data: bytes, pos: int):
    r = Reader(data, pos)
    fmt = r.u16()
    if fmt == 1:
        start = r.u16()
        values = r.array("H", r.u16())
        return lambda g: values[g - start] if 0 <= g - start < len(values) else 0
    ranges = sorted(r.array("H", 3) for _ in range(r.u16()))
    starts = [s for s, _, _ in ranges]

    def lookup(g):
        i = bisect.bisect_right(starts, g) - 1
        return ranges[i][2] if i >= 0 and g <= ranges[i][1] else 0

    return lookup


def _value_size(fmt: int) -> int:
    return 2 * bin(fmt & 0xFF).count("1")


def _x_adjust(data: bytes, pos: int, fmt: int) -> int:
    total, r = 0, Reader(data, pos)
    for bit in (1, 2, 4, 8):
        if fmt & bit:
            v = r.i16()
            if bit in (X_PLACEMENT, X_ADVANCE):
                total += v
    return total


def _pair_subtable(data: bytes, pos: int):
    r = Reader(data, pos)
    fmt, cov_off, vf1, vf2 = r.u16(), r.u16(), r.u16(), r.u16()
    coverage = _coverage(data, pos + cov_off)
    size1, size2 = _value_size(vf1), _value_size(vf2)
    if fmt == 1:
        set_offsets = r.array("H", r.u16())

        def lookup(left, right):
            i = coverage(left)
            if i is None or i >= len(set_offsets):
                return None
            sp = pos + set_offsets[i]
            count = Reader(data, sp).u16()
            rec = 2 + size1 + size2
            lo, hi = 0, count
            while lo < hi:
                mid = (lo + hi) // 2
                g = Reader(data, sp + 2 + mid * rec).u16()
                if g == right:
                    return _x_adjust(data, sp + 4 + mid * rec, vf1)
                lo, hi = (mid + 1, hi) if g < right else (lo, mid)
            return None

        return lookup
    if fmt != 2:
        return None
    cd1_off, cd2_off, n1, n2 = r.u16(), r.u16(), r.u16(), r.u16()
    class1, class2 = _class_def(data, pos + cd1_off), _class_def(data, pos + cd2_off)
    records = r.pos
    rec = size1 + size2

    def lookup(left, right):
        if coverage(left) is None:
            return None
        c1, c2 = class1(left), class2(right)
        if c1 >= n1 or c2 >= n2:
            return None
        return _x_adjust(data, records + (c1 * n2 + c2) * rec, vf1)

    return lookup


def read_gpos_kerning(data: bytes, offset: int) -> list:
    """Pair-adjustment subtable lookups reachable from the ``kern`` feature."""
    r = Reader(data, offset + 6)
    feature_list = offset + r.u16()
    lookup_list = offset + r.u16()
    fr = Reader(data, feature_list)
    indices: list[int] = []
    for _ in range(fr.u16()):
        tag, foff = fr.tag(), fr.u16()
        if tag != KERN_FEATURE:
            continue
        f = Reader(data, feature_list + foff + 2)
        for idx in f.array("H", f.u16()):
            if idx not in indices:
                indices.append(idx)
    lr = Reader(data, lookup_list)
    lookup_offsets = lr.array("H", lr.u16())
    subtables = []
    for idx in sorted(indices):
        if idx >= len(lookup_offsets):
            continue
        lp = lookup_list + lookup_offsets[idx]
        lk = Reader(data, lp)
        kind, _, count = lk.u16(), lk.u16(), lk.u16()
        for sub_off in lk.array("H", count):
            sp, sub_kind = lp + sub_off, kind
            if kind == EXTENSION:
                ext = Reader(data, sp + 2)
                sub_kind = ext.u16()
                sp += ext.u32()
            if sub_kind == PAIR_ADJUSTMENT:
                fn = _pair_subtable(data, sp)
                if fn is not None:
                    subtables.append(fn)
    return subtables


def read_kern_table(data: bytes, offset: int) -> dict[tuple[int, int], int]:
    """Horizontal format 0 pairs of a Microsoft-style ``kern`` table."""
    r = Reader(data, offset)
    if r.u16() != 0:
        return {}
    pairs: dict[tuple[int, int], int] = {}
    for _ in range(r.u16()):
        start = r.pos
        _, length, coverage = r.u16(), r.u16(), r.u16()
        if coverage >> 8 == KERN_FORMAT0 and coverage & KERN_HORIZONTAL and not coverage & KERN_CROSS_STREAM:
            n = r.u16()
            r.pos += 6
            flat = r.array("H", 3 * n)
            for i in range(n):
                v = flat[3 * i + 2]
                pairs[(flat[3 * i], flat[3 * i + 1])] = v - 0x10000 if v >= 0x8000 else v
        r.pos = start + length
    return pairs


class Kerning:
    """Combined ``GPOS`` and ``kern`` pair adjustments with a cache."""

    def __init__(self, gpos: list, kern: dict[tuple[int, int], int]):
        self._gpos = gpos
        self._kern = kern
        self._cache: dict[tuple[int, int], int] = {}

    def __bool__(self) -> bool:
        return bool(self._gpos or self._kern)

    def __call__(self, left: int, right: int) -> int:
        key = (left, right)
        if key in self._cache:
            return self._cache[key]
        value = 0
        if self._gpos:
            for fn in self._gpos:
                found = fn(left, right)
                if found is not None:
                    value = found
                    break
        else:
            value = self._kern.get(key, 0)
        self._cache[key] = value
        return value
