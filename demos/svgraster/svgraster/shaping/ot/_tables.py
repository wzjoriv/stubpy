"""Shared OpenType layout structures: coverage, class definitions, lookups, script/feature lists and GDEF."""
from __future__ import annotations

import bisect
import struct
from dataclasses import dataclass, field

_U16 = struct.Struct(">H")
_I16 = struct.Struct(">h")
_U32 = struct.Struct(">I")
DEFAULT_SCRIPT = b"DFLT"
DEFAULT_LANG = b"dflt"
LATIN = b"latn"
NO_REQUIRED = 0xFFFF
USE_MARK_FILTERING_SET = 0x0010
GLYPH_BASE, GLYPH_LIGATURE, GLYPH_MARK, GLYPH_COMPONENT = 1, 2, 3, 4


def u16(data: bytes, pos: int) -> int:
    """An unsigned 16-bit value at ``pos``."""
    return _U16.unpack_from(data, pos)[0]


def i16(data: bytes, pos: int) -> int:
    """A signed 16-bit value at ``pos``."""
    return _I16.unpack_from(data, pos)[0]


def u32(data: bytes, pos: int) -> int:
    """An unsigned 32-bit value at ``pos``."""
    return _U32.unpack_from(data, pos)[0]


def u16s(data: bytes, pos: int, count: int) -> tuple[int, ...]:
    """``count`` unsigned 16-bit values starting at ``pos``."""
    return struct.unpack_from(f">{count}H", data, pos) if count else ()


def offsets(data: bytes, base: int, pos: int, count: int) -> list[int]:
    """``count`` 16-bit offsets at ``pos``, made absolute against ``base``."""
    return [base + o for o in u16s(data, pos, count)]


class Coverage:
    """Glyph id to coverage index."""

    __slots__ = ("_map", "_starts", "_ranges")

    def __init__(self, data: bytes, pos: int):
        fmt, count = u16(data, pos), u16(data, pos + 2)
        self._map: dict[int, int] | None = None
        if fmt == 1:
            self._map = {g: i for i, g in enumerate(u16s(data, pos + 4, count))}
            return
        flat = u16s(data, pos + 4, 3 * count)
        self._ranges = [flat[k:k + 3] for k in range(0, len(flat), 3)]
        self._starts = [r[0] for r in self._ranges]

    def __call__(self, gid: int) -> int | None:
        if self._map is not None:
            return self._map.get(gid)
        i = bisect.bisect_right(self._starts, gid) - 1
        if i >= 0:
            start, end, index = self._ranges[i]
            if gid <= end:
                return index + gid - start
        return None

    def __contains__(self, gid: int) -> bool:
        return self(gid) is not None


class ClassDef:
    """Glyph id to class (0 when unlisted)."""

    __slots__ = ("_start", "_values", "_starts", "_ranges")

    def __init__(self, data: bytes | None = None, pos: int = 0):
        self._values: tuple[int, ...] = ()
        self._start = 0
        self._starts: list[int] = []
        self._ranges: list[tuple[int, ...]] = []
        if data is None or pos == 0:
            return
        fmt = u16(data, pos)
        if fmt == 1:
            self._start = u16(data, pos + 2)
            self._values = u16s(data, pos + 6, u16(data, pos + 4))
            return
        count = u16(data, pos + 2)
        flat = u16s(data, pos + 4, 3 * count)
        self._ranges = sorted(flat[k:k + 3] for k in range(0, len(flat), 3))
        self._starts = [r[0] for r in self._ranges]

    def __call__(self, gid: int) -> int:
        if self._values:
            k = gid - self._start
            return self._values[k] if 0 <= k < len(self._values) else 0
        i = bisect.bisect_right(self._starts, gid) - 1
        return self._ranges[i][2] if i >= 0 and gid <= self._ranges[i][1] else 0


@dataclass
class Lookup:
    """A lookup's type, flags and absolute subtable offsets (extensions resolved)."""

    kind: int
    flag: int
    subtables: list[int]
    mark_set: int = -1
    parsed: list | None = field(default=None, repr=False)


def read_lookup(data: bytes, pos: int, extension: int) -> Lookup:
    """Parse a lookup header, following extension subtables."""
    kind, flag, count = u16(data, pos), u16(data, pos + 2), u16(data, pos + 4)
    subs = offsets(data, pos, pos + 6, count)
    mark_set = u16(data, pos + 6 + 2 * count) if flag & USE_MARK_FILTERING_SET else -1
    if kind == extension and subs:
        kind = u16(data, subs[0] + 2)
        subs = [s + u32(data, s + 4) for s in subs]
    return Lookup(kind, flag, subs, mark_set)


class LayoutTable:
    """The script, feature and lookup lists shared by GSUB and GPOS."""

    def __init__(self, data: bytes, pos: int, extension: int):
        self.data = data
        self.extension = extension
        script_list, feature_list, lookup_list = u16s(data, pos + 4, 3)
        self.scripts = self._scripts(data, pos + script_list)
        fl = pos + feature_list
        self.features: list[tuple[bytes, tuple[int, ...]]] = []
        for k in range(u16(data, fl)):
            rec = fl + 2 + 6 * k
            tag, foff = data[rec:rec + 4], fl + u16(data, rec + 4)
            self.features.append((tag, u16s(data, foff + 4, u16(data, foff + 2))))
        ll = pos + lookup_list
        self._lookup_offsets = offsets(data, ll, ll + 2, u16(data, ll))
        self._lookups: dict[int, Lookup] = {}

    @staticmethod
    def _scripts(data: bytes, base: int) -> dict[bytes, dict[bytes, int]]:
        out = {}
        for k in range(u16(data, base)):
            rec = base + 2 + 6 * k
            tag, soff = data[rec:rec + 4], base + u16(data, rec + 4)
            langs = {}
            default = u16(data, soff)
            if default:
                langs[DEFAULT_LANG] = soff + default
            for j in range(u16(data, soff + 2)):
                lrec = soff + 4 + 6 * j
                langs[data[lrec:lrec + 4]] = soff + u16(data, lrec + 4)
            out[tag] = langs
        return out

    def __len__(self) -> int:
        return len(self._lookup_offsets)

    def lookup(self, index: int) -> Lookup:
        """Lookup ``index``, parsed on first use."""
        found = self._lookups.get(index)
        if found is None:
            found = self._lookups[index] = read_lookup(self.data, self._lookup_offsets[index], self.extension)
        return found

    def select_script(self, tags: list[bytes]) -> bytes | None:
        """The first of ``tags`` (then ``DFLT``, ``dflt``, ``latn``) the table supports."""
        for tag in [*tags, DEFAULT_SCRIPT, DEFAULT_LANG, LATIN]:
            if tag in self.scripts:
                return tag
        return None

    def feature_lookups(self, script: bytes | None, lang: bytes | None) -> dict[bytes, list[int]]:
        """Feature tag to lookup indices for a script and language system."""
        langs = self.scripts.get(script or b"", {})
        pos = langs.get(lang or b"") or langs.get(DEFAULT_LANG)
        if pos is None:
            return {}
        data = self.data
        required = u16(data, pos + 2)
        indices = list(u16s(data, pos + 6, u16(data, pos + 4)))
        if required != NO_REQUIRED:
            indices.append(required)
        out: dict[bytes, list[int]] = {}
        for idx in indices:
            if idx < len(self.features):
                tag, lookups = self.features[idx]
                out.setdefault(tag, []).extend(lk for lk in lookups if lk < len(self))
        return out


class Gdef:
    """Glyph classes, mark attachment classes and mark filtering sets."""

    def __init__(self, data: bytes | None = None, pos: int = 0):
        self.present = data is not None
        self.glyph_class = ClassDef()
        self.mark_class = ClassDef()
        self.mark_sets: list[Coverage] = []
        if data is None:
            return
        minor = u16(data, pos + 2)
        gc, _, _, mac = u16s(data, pos + 4, 4)
        self.glyph_class = ClassDef(data, pos + gc if gc else 0)
        self.mark_class = ClassDef(data, pos + mac if mac else 0)
        if minor >= 2:
            sets = u16(data, pos + 12)
            if sets:
                base = pos + sets
                self.mark_sets = [Coverage(data, base + u32(data, base + 4 + 4 * k)) for k in range(u16(data, base + 2))]

    def in_mark_set(self, index: int, gid: int) -> bool:
        """Whether ``gid`` belongs to mark filtering set ``index``."""
        return 0 <= index < len(self.mark_sets) and gid in self.mark_sets[index]
