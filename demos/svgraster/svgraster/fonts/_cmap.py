"""Character to glyph mapping (``cmap`` formats 0, 4, 6 and 12)."""
from __future__ import annotations

import bisect

from ._reader import Reader

SYMBOL_BASE = 0xF000
# (platform, encoding) in order of preference.
PREFERRED = ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0), (3, 0), (1, 0))
SYMBOL_ENCODING = (3, 0)


class CharMap:
    """Segment-based code point lookup."""

    def __init__(self, starts: list[int], ends: list[int], deltas: list[int], mappers: list, symbol: bool = False):
        self._starts = starts
        self._ends = ends
        self._deltas = deltas
        self._mappers = mappers
        self.symbol = symbol

    def __call__(self, codepoint: int) -> int:
        gid = self._lookup(codepoint)
        if gid == 0 and self.symbol and codepoint < 0x100:
            gid = self._lookup(SYMBOL_BASE + codepoint)
        return gid

    def _lookup(self, cp: int) -> int:
        i = bisect.bisect_right(self._starts, cp) - 1
        if i < 0 or cp > self._ends[i]:
            return 0
        mapper = self._mappers[i]
        if mapper is not None:
            return mapper(cp)
        return (cp + self._deltas[i]) & 0xFFFF if self._deltas[i] is not None else 0

    def codepoints(self) -> int:
        """The number of code points covered by the segments."""
        return sum(e - s + 1 for s, e in zip(self._starts, self._ends))


def _format0(r: Reader) -> CharMap:
    r.pos += 4
    ids = r.array("B", 256)
    return CharMap([0], [255], [None], [lambda cp: ids[cp]])


def _format4(r: Reader, data: bytes) -> CharMap:
    r.pos += 4
    seg_x2 = r.u16()
    n = seg_x2 // 2
    r.pos += 6
    ends = list(r.array("H", n))
    r.u16()
    starts = list(r.array("H", n))
    deltas = list(r.array("h", n))
    range_pos = r.pos
    offsets = list(r.array("H", n))
    mappers: list = []
    for i in range(n):
        if offsets[i] == 0:
            mappers.append(None)
            continue
        base = range_pos + 2 * i + offsets[i]

        def mapper(cp, base=base, start=starts[i], delta=deltas[i]):
            pos = base + 2 * (cp - start)
            if pos + 2 > len(data):
                return 0
            g = int.from_bytes(data[pos:pos + 2], "big")
            return (g + delta) & 0xFFFF if g else 0

        mappers.append(mapper)
    order = sorted(range(n), key=lambda k: starts[k])
    return CharMap([starts[k] for k in order], [ends[k] for k in order], [deltas[k] for k in order],
                   [mappers[k] for k in order])


def _format6(r: Reader) -> CharMap:
    r.pos += 4
    first, count = r.u16(), r.u16()
    ids = r.array("H", count)
    return CharMap([first], [first + count - 1], [None], [lambda cp: ids[cp - first]])


def _format12(r: Reader) -> CharMap:
    r.pos += 10
    n = r.u32()
    flat = r.array("I", 3 * n)
    starts, ends, mappers = list(flat[0::3]), list(flat[1::3]), []
    for start, glyph in zip(starts, flat[2::3]):
        mappers.append(lambda cp, s=start, g=glyph: g + cp - s)
    return CharMap(starts, ends, [None] * n, mappers)


PARSERS = {0: _format0, 6: _format6, 12: _format12}


def read_cmap(data: bytes, offset: int) -> CharMap:
    """The best Unicode subtable of the ``cmap`` at ``offset``."""
    r = Reader(data, offset + 2)
    count = r.u16()
    subtables = {}
    for _ in range(count):
        platform, encoding, sub_off = r.u16(), r.u16(), r.u32()
        subtables.setdefault((platform, encoding), offset + sub_off)
    for key in PREFERRED:
        if key not in subtables:
            continue
        sub = Reader(data, subtables[key])
        fmt = sub.u16()
        if fmt == 4:
            cmap = _format4(sub, data)
        elif fmt in PARSERS:
            cmap = PARSERS[fmt](sub)
        else:
            continue
        cmap.symbol = key == SYMBOL_ENCODING
        return cmap
    return CharMap([], [], [], [])
