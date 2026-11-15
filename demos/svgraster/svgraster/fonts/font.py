"""The :class:`Font` face: metrics, character mapping, kerning and glyph outlines."""
from __future__ import annotations

import math
import os
from pathlib import Path as FilePath

import numpy as np

from ..dom.transform import Matrix
from ..parse.flatten import flatten_path
from ..parse.pathdata import Path
from . import _tables as T
from ._cff import CffOutlines
from ._cmap import CharMap, read_cmap
from ._glyf import GlyfOutlines
from ._kerning import Kerning, read_gpos_kerning, read_kern_table
from ._reader import FontFormatError, collection_offsets, table_directory

MAX_CACHED_GLYPHS = 4096
TOLERANCE_BUCKET = 2.0


class Font:
    """A parsed TrueType (``glyf``) or OpenType (``CFF``) face.

    Lengths are in font units; ``units_per_em`` converts them to ems.
    """

    def __init__(self, data: bytes, index: int = 0, source: str | None = None):
        offsets = collection_offsets(data)
        if not 0 <= index < len(offsets):
            raise FontFormatError(f"font index {index} out of range (file has {len(offsets)})")
        version, tables = table_directory(data, offsets[index])
        T.require(tables, b"head", b"hhea", b"maxp", b"hmtx", b"cmap")
        self.source = source
        self.index = index
        self.metrics = m = T.Metrics()
        mac_style = T.read_head(data, tables[b"head"][0], m)
        T.read_hhea(data, tables[b"hhea"][0], m)
        T.read_maxp(data, tables[b"maxp"][0], m)
        names = T.read_name(data, tables[b"name"][0]) if b"name" in tables else {}
        self.naming = T.naming_from(names, mac_style)
        if b"OS/2" in tables:
            T.read_os2(data, *tables[b"OS/2"], m, self.naming)
        if b"post" in tables:
            T.read_post(data, tables[b"post"][0], m)
        self.advances, _ = T.read_hmtx(data, tables[b"hmtx"][0], m)
        self.cmap: CharMap = read_cmap(data, tables[b"cmap"][0])
        if b"glyf" in tables and b"loca" in tables:
            self._outlines = GlyfOutlines(data, tables[b"glyf"], tables[b"loca"], m.index_to_loc == 1, m.num_glyphs)
            self.outline_format = "glyf"
        elif b"CFF " in tables:
            self._outlines = CffOutlines(data, tables[b"CFF "][0])
            self.outline_format = "cff"
        else:
            raise FontFormatError("font has neither glyf nor CFF outlines")
        gpos = read_gpos_kerning(data, tables[b"GPOS"][0]) if b"GPOS" in tables else []
        kern = read_kern_table(data, tables[b"kern"][0]) if b"kern" in tables else {}
        self.kerning = Kerning(gpos, kern)
        self._paths: dict[int, Path] = {}
        self._polys: dict[tuple[int, int], list[np.ndarray]] = {}

    @classmethod
    def from_file(cls, path: str | os.PathLike, index: int = 0) -> Font:
        """Load the face at ``index`` of a ``.ttf``, ``.otf`` or ``.ttc`` file."""
        return cls(FilePath(path).read_bytes(), index, os.fspath(path))

    def __repr__(self) -> str:
        style = "italic" if self.italic else "normal"
        return f"<Font {self.family!r} {self.weight} {style} ({self.outline_format}, {self.num_glyphs} glyphs)>"

    @property
    def family(self) -> str:
        """The (typographic) family name."""
        return self.naming.family

    @property
    def weight(self) -> int:
        """The CSS weight class, 100 to 900."""
        return self.naming.weight

    @property
    def italic(self) -> bool:
        """Whether the face is italic or oblique."""
        return self.naming.italic

    @property
    def units_per_em(self) -> int:
        """Font units per em."""
        return self.metrics.units_per_em

    @property
    def num_glyphs(self) -> int:
        """Glyphs in the face."""
        return self.metrics.num_glyphs

    def glyph_index(self, char: str) -> int:
        """The glyph id for ``char``; 0 (``.notdef``) when unmapped."""
        gid = self.cmap(ord(char))
        return gid if gid < self.num_glyphs else 0

    def map_text(self, text: str) -> list[tuple[int, int]]:
        """``(glyph id, characters consumed)`` for each character."""
        return [(self.glyph_index(ch), 1) for ch in text]

    def has_glyph(self, char: str) -> bool:
        """Whether ``char`` maps to a real glyph."""
        return self.glyph_index(char) != 0

    def advance(self, gid: int) -> float:
        """Horizontal advance in font units."""
        return float(self.advances[gid]) if 0 <= gid < len(self.advances) else 0.0

    def kern(self, left: int, right: int) -> float:
        """Pair adjustment in font units (negative tightens)."""
        return float(self.kerning(left, right)) if self.kerning else 0.0

    def outline(self, gid: int) -> Path:
        """The glyph outline in font units, y up."""
        path = self._paths.get(gid)
        if path is None:
            path = self._outlines.outline(gid)
            if len(self._paths) < MAX_CACHED_GLYPHS:
                self._paths[gid] = path
        return path

    def text_width(self, text: str, size: float = 1.0) -> float:
        """Advance of ``text`` with kerning at font size ``size``."""
        total, prev = 0.0, None
        for ch in text:
            gid = self.glyph_index(ch)
            if prev is not None:
                total += self.kern(prev, gid)
            total += self.advance(gid)
            prev = gid
        return total * size / self.units_per_em

    def glyph_polygons(self, gid: int, to_user: Matrix, tolerance: float) -> list[np.ndarray]:
        """Flattened glyph contours mapped by ``to_user`` (font units to user space)."""
        scale = to_user.mean_scale or 1.0
        bucket = int(math.floor(math.log(max(tolerance / scale, 1e-6), TOLERANCE_BUCKET)))
        key = (gid, bucket)
        polys = self._polys.get(key)
        if polys is None:
            polys = [p.points for p in flatten_path(self.outline(gid), TOLERANCE_BUCKET ** bucket) if len(p.points) > 2]
            if len(self._polys) < MAX_CACHED_GLYPHS:
                self._polys[key] = polys
        return [to_user.apply_points(p) for p in polys]

    def scaled(self, value: float, size: float) -> float:
        """A font-unit ``value`` in user units at font size ``size``."""
        return value * size / self.units_per_em


def font_faces(path: str | os.PathLike) -> list[Font]:
    """Every face in a font file (several for a ``.ttc``)."""
    data = FilePath(path).read_bytes()
    return [Font(data, i, os.fspath(path)) for i in range(len(collection_offsets(data)))]
