"""Cheap face descriptions read with seeks (no full parse) and system font folders."""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import _tables as T
from ._reader import OFFSET_TABLE, TABLE_RECORD, TTC_TAG, FontFormatError

FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
FONT_PATH_ENV = "SVGRASTER_FONT_PATH"
NAME_TABLES = (b"name", b"OS/2", b"head")
MAX_SCAN_DEPTH = 6


@dataclass(frozen=True)
class FaceInfo:
    """Where a face lives and how it is classified."""

    path: str
    index: int
    family: str
    weight: int
    italic: bool
    aliases: frozenset[str] = field(default_factory=frozenset)

    @property
    def key(self) -> tuple[str, int]:
        """``(path, index)``."""
        return (self.path, self.index)


def system_font_dirs() -> list[Path]:
    """Font folders for this platform plus ``SVGRASTER_FONT_PATH`` entries."""
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        dirs = [windir / "Fonts", local / "Microsoft" / "Windows" / "Fonts"]
    elif sys.platform == "darwin":
        dirs = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        dirs = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), data_home / "fonts", home / ".fonts"]
    extra = [Path(p) for p in os.environ.get(FONT_PATH_ENV, "").split(os.pathsep) if p]
    return extra + [d for d in dirs if d.is_dir()]


def font_files(root: Path) -> list[Path]:
    """Font files under ``root`` (a file or a folder searched recursively)."""
    if root.is_file():
        return [root] if root.suffix.lower() in FONT_SUFFIXES else []
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if len(Path(dirpath).relative_to(root).parts) >= MAX_SCAN_DEPTH:
            dirnames.clear()
        found.extend(Path(dirpath) / f for f in filenames if f.lower().endswith(FONT_SUFFIXES))
    return sorted(found)


def _read(fh, pos: int, size: int) -> bytes:
    fh.seek(pos)
    data = fh.read(size)
    if len(data) != size:
        raise FontFormatError("truncated font file")
    return data


def _describe_face(fh, path: str, index: int, offset: int) -> FaceInfo:
    _, num_tables, _, _, _ = OFFSET_TABLE.unpack(_read(fh, offset, OFFSET_TABLE.size))
    directory = _read(fh, offset + OFFSET_TABLE.size, num_tables * TABLE_RECORD.size)
    tables = {}
    for i in range(num_tables):
        tag, _, toff, length = TABLE_RECORD.unpack_from(directory, i * TABLE_RECORD.size)
        tables[tag] = (toff, length)
    names = {}
    if b"name" in tables:
        toff, length = tables[b"name"]
        names = T.read_name(_read(fh, toff, length), 0)
    mac_style = 0
    if b"head" in tables:
        mac_style = struct.unpack(">H", _read(fh, tables[b"head"][0] + 44, 2))[0]
    naming = T.naming_from(names, mac_style)
    if b"OS/2" in tables:
        toff, length = tables[b"OS/2"]
        os2 = _read(fh, toff, length)
        naming.weight = struct.unpack_from(">H", os2, 4)[0] or naming.weight
        naming.italic = naming.italic or bool(struct.unpack_from(">H", os2, 62)[0] & (T.FS_ITALIC | T.FS_OBLIQUE))
    if not naming.family:
        naming.family = Path(path).stem
    aliases = frozenset(naming.aliases | {naming.family.lower()})
    return FaceInfo(path, index, naming.family, naming.weight, naming.italic, aliases)


def describe(path: str | os.PathLike) -> list[FaceInfo]:
    """Describe every face in a font file; unreadable files give an empty list."""
    path = os.fspath(path)
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
            offsets = [0]
            if head[:4] == TTC_TAG:
                count = struct.unpack_from(">I", head, 8)[0]
                offsets = list(struct.unpack(f">{count}I", _read(fh, 12, 4 * count)))
            return [_describe_face(fh, path, i, off) for i, off in enumerate(offsets)]
    except (OSError, FontFormatError, struct.error, UnicodeDecodeError, IndexError, ValueError):
        return []
