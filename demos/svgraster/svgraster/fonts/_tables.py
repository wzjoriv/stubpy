"""Metric and naming tables: ``head``, ``hhea``, ``maxp``, ``hmtx``, ``OS/2``, ``post`` and ``name``."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ._reader import FontFormatError, Reader

NAME_FAMILY = 1
NAME_SUBFAMILY = 2
NAME_FULL = 4
NAME_TYPO_FAMILY = 16
NAME_TYPO_SUBFAMILY = 17
PLATFORM_UNICODE = 0
PLATFORM_MAC = 1
PLATFORM_WINDOWS = 3
WINDOWS_ENGLISH_US = 0x0409
FS_ITALIC = 0x0001
FS_BOLD = 0x0020
FS_OBLIQUE = 0x0200
MAC_BOLD = 0x01
MAC_ITALIC = 0x02
DEFAULT_WEIGHT = 400
BOLD_WEIGHT = 700
OS2_X_HEIGHT_VERSION = 2


@dataclass
class Metrics:
    """Global font metrics in font units."""

    units_per_em: int = 1000
    ascent: int = 800
    descent: int = -200
    line_gap: int = 0
    x_height: int = 0
    cap_height: int = 0
    underline_position: int = -100
    underline_thickness: int = 50
    strikeout_position: int = 0
    strikeout_size: int = 0
    index_to_loc: int = 0
    num_glyphs: int = 0
    num_h_metrics: int = 0


@dataclass
class Naming:
    """Family, style and classification from ``name``, ``OS/2`` and ``head``."""

    family: str = ""
    subfamily: str = ""
    full_name: str = ""
    weight: int = DEFAULT_WEIGHT
    italic: bool = False
    aliases: set[str] = field(default_factory=set)


def read_head(data: bytes, offset: int, m: Metrics) -> int:
    """Fill units per em and the ``loca`` format; return ``macStyle``."""
    r = Reader(data, offset + 18)
    m.units_per_em = r.u16() or 1000
    mac_style = Reader(data, offset + 44).u16()
    m.index_to_loc = Reader(data, offset + 50).i16()
    return mac_style


def read_hhea(data: bytes, offset: int, m: Metrics) -> None:
    """Fill ascent, descent, line gap and the horizontal metric count."""
    r = Reader(data, offset + 4)
    m.ascent, m.descent, m.line_gap = r.i16(), r.i16(), r.i16()
    m.num_h_metrics = Reader(data, offset + 34).u16()


def read_maxp(data: bytes, offset: int, m: Metrics) -> None:
    """Fill the glyph count."""
    m.num_glyphs = Reader(data, offset + 4).u16()


def read_hmtx(data: bytes, offset: int, m: Metrics) -> tuple[np.ndarray, np.ndarray]:
    """Advance widths and left side bearings for every glyph."""
    n = max(1, m.num_h_metrics)
    pairs = np.frombuffer(data, dtype=">u2", count=2 * n, offset=offset).reshape(n, 2)
    advances = np.empty(max(m.num_glyphs, n), dtype=np.int32)
    advances[:n] = pairs[:, 0]
    advances[n:] = pairs[-1, 0]
    lsb = np.zeros(len(advances), dtype=np.int32)
    lsb[:n] = pairs[:, 1].astype(np.int16)
    return advances, lsb


def read_os2(data: bytes, offset: int, length: int, m: Metrics, naming: Naming) -> None:
    """Weight, italic flags, strikeout and typographic heights."""
    r = Reader(data, offset)
    version = r.u16()
    naming.weight = Reader(data, offset + 4).u16() or DEFAULT_WEIGHT
    sel = Reader(data, offset + 62).u16()
    naming.italic = naming.italic or bool(sel & (FS_ITALIC | FS_OBLIQUE))
    r = Reader(data, offset + 26)
    m.strikeout_size, m.strikeout_position = r.i16(), r.i16()
    if version >= OS2_X_HEIGHT_VERSION and length >= 90:
        r = Reader(data, offset + 86)
        m.x_height, m.cap_height = r.i16(), r.i16()


def read_post(data: bytes, offset: int, m: Metrics) -> None:
    """Underline position and thickness."""
    r = Reader(data, offset + 8)
    m.underline_position, m.underline_thickness = r.i16(), r.i16()


def _decode_name(raw: bytes, platform: int) -> str:
    if platform in (PLATFORM_UNICODE, PLATFORM_WINDOWS):
        return raw.decode("utf-16-be", errors="replace")
    return raw.decode("mac_roman", errors="replace")


def read_name(data: bytes, offset: int) -> dict[int, str]:
    """Name records by id, preferring Windows US English, then any Unicode, then Mac."""
    r = Reader(data, offset)
    r.u16()
    count, storage = r.u16(), r.u16()
    found: dict[int, tuple[int, str]] = {}
    for _ in range(count):
        platform, encoding, language, name_id, length, str_off = r.array("H", 6)
        if name_id not in (NAME_FAMILY, NAME_SUBFAMILY, NAME_FULL, NAME_TYPO_FAMILY, NAME_TYPO_SUBFAMILY):
            continue
        start = offset + storage + str_off
        if start + length > len(data):
            continue
        rank = 0 if (platform, language) == (PLATFORM_WINDOWS, WINDOWS_ENGLISH_US) else (
            1 if platform in (PLATFORM_UNICODE, PLATFORM_WINDOWS) else 2)
        if name_id not in found or rank < found[name_id][0]:
            found[name_id] = (rank, _decode_name(data[start:start + length], platform))
    return {k: v for k, (_, v) in found.items()}


def naming_from(names: dict[int, str], mac_style: int) -> Naming:
    """Family and style information from name records and ``macStyle``."""
    family = names.get(NAME_TYPO_FAMILY) or names.get(NAME_FAMILY) or ""
    subfamily = names.get(NAME_TYPO_SUBFAMILY) or names.get(NAME_SUBFAMILY) or ""
    naming = Naming(family=family, subfamily=subfamily, full_name=names.get(NAME_FULL, family))
    naming.aliases = {n.lower() for n in (names.get(NAME_FAMILY), names.get(NAME_TYPO_FAMILY),
                                          names.get(NAME_FULL)) if n}
    naming.italic = bool(mac_style & MAC_ITALIC) or "italic" in subfamily.lower() or "oblique" in subfamily.lower()
    if mac_style & MAC_BOLD:
        naming.weight = BOLD_WEIGHT
    return naming


def require(tables: dict, *tags: bytes) -> None:
    """Raise :class:`FontFormatError` unless every table in ``tags`` is present."""
    missing = [t.decode("latin-1") for t in tags if t not in tables]
    if missing:
        raise FontFormatError(f"font is missing required tables: {', '.join(missing)}")
