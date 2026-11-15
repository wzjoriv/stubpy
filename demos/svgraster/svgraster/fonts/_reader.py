"""Big-endian binary reading and the sfnt table directory (including TTC)."""
from __future__ import annotations

import struct

TTC_TAG = b"ttcf"
TRUETYPE_TAGS = (b"\x00\x01\x00\x00", b"true")
CFF_TAG = b"OTTO"
TABLE_RECORD = struct.Struct(">4sIII")
OFFSET_TABLE = struct.Struct(">4sHHHH")


class FontFormatError(ValueError):
    """Raised for files that are not usable TrueType/OpenType fonts."""


class Reader:
    """A bounds-checked cursor over font bytes."""

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def _take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise FontFormatError("unexpected end of font data")
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return values

    def u8(self) -> int:
        """An unsigned byte."""
        return self._take(">B")[0]

    def u16(self) -> int:
        """An unsigned 16-bit integer."""
        return self._take(">H")[0]

    def i16(self) -> int:
        """A signed 16-bit integer."""
        return self._take(">h")[0]

    def u32(self) -> int:
        """An unsigned 32-bit integer."""
        return self._take(">I")[0]

    def i32(self) -> int:
        """A signed 32-bit integer."""
        return self._take(">i")[0]

    def fixed(self) -> float:
        """A 16.16 fixed-point number."""
        return self.i32() / 65536.0

    def f2dot14(self) -> float:
        """A 2.14 fixed-point number."""
        return self.i16() / 16384.0

    def array(self, fmt: str, count: int) -> tuple:
        """``count`` values of struct format character ``fmt``."""
        return self._take(f">{count}{fmt}") if count else ()

    def tag(self) -> bytes:
        """A four-byte tag."""
        return self._take(">4s")[0]

    def at(self, pos: int) -> Reader:
        """A new reader at absolute offset ``pos``."""
        return Reader(self.data, pos)


def collection_offsets(data: bytes) -> list[int]:
    """Offsets of each font in a file (one entry unless it is a TTC)."""
    if data[:4] != TTC_TAG:
        return [0]
    r = Reader(data, 8)
    count = r.u32()
    return list(r.array("I", count))


def table_directory(data: bytes, offset: int = 0) -> tuple[bytes, dict[bytes, tuple[int, int]]]:
    """The sfnt version tag and ``{tag: (offset, length)}`` for the font at ``offset``."""
    if len(data) < offset + OFFSET_TABLE.size:
        raise FontFormatError("file too short for a font")
    version, num_tables, _, _, _ = OFFSET_TABLE.unpack_from(data, offset)
    if version not in TRUETYPE_TAGS and version != CFF_TAG:
        raise FontFormatError(f"unsupported font signature {version!r}")
    tables = {}
    pos = offset + OFFSET_TABLE.size
    for _ in range(num_tables):
        if pos + TABLE_RECORD.size > len(data):
            raise FontFormatError("truncated table directory")
        tag, _, toff, length = TABLE_RECORD.unpack_from(data, pos)
        if toff + length > len(data):
            raise FontFormatError(f"table {tag!r} extends past the end of the file")
        tables[tag] = (toff, length)
        pos += TABLE_RECORD.size
    return version, tables
