"""OpenType layout: GSUB and GPOS lookups with GDEF glyph classes.

Usage::

    layout = OpenTypeLayout(data, tables)
    lookups = layout.lookups(layout.gsub, [b"arab"], None, {b"init": mask})
"""
from __future__ import annotations

from ._engine import ATTACH_CURSIVE, ATTACH_MARK, Applier, Info, synthetic_class
from ._gpos import parse_gpos
from ._gsub import REVERSE, parse_gsub
from ._tables import GLYPH_BASE, GLYPH_LIGATURE, GLYPH_MARK, Gdef, LayoutTable

GSUB_EXTENSION = 7
GPOS_EXTENSION = 9


class OpenTypeLayout:
    """The ``GSUB``, ``GPOS`` and ``GDEF`` tables of one face."""

    def __init__(self, data: bytes, tables: dict[bytes, tuple[int, int]]):
        self.gsub = LayoutTable(data, tables[b"GSUB"][0], GSUB_EXTENSION) if b"GSUB" in tables else None
        self.gpos = LayoutTable(data, tables[b"GPOS"][0], GPOS_EXTENSION) if b"GPOS" in tables else None
        self.gdef = Gdef(data, tables[b"GDEF"][0]) if b"GDEF" in tables else Gdef()

    @staticmethod
    def features(table: LayoutTable | None, scripts: list[bytes], lang: bytes | None) -> dict[bytes, list[int]]:
        """Feature tag to lookups for the best script and language of ``table``."""
        if table is None:
            return {}
        return table.feature_lookups(table.select_script(scripts), lang)

    @staticmethod
    def lookups(available: dict[bytes, list[int]], masks: dict[bytes, int]) -> list[tuple[int, int]]:
        """``(lookup index, mask)`` for the enabled features, in lookup order."""
        out: dict[int, int] = {}
        for tag, mask in masks.items():
            for index in available.get(tag, ()):
                out[index] = out.get(index, 0) | mask
        return sorted(out.items())

    def substitute(self, buf: list[Info], lookups: list[tuple[int, int]], rtl: bool) -> None:
        """Apply GSUB ``lookups`` to ``buf`` in place."""
        if self.gsub is None:
            return
        ctx = Applier(self.gsub, self.gdef, buf, parse_gsub, rtl)
        for index, mask in lookups:
            ctx.run(index, mask, reverse=self.gsub.lookup(index).kind == REVERSE)

    def position(self, buf: list[Info], lookups: list[tuple[int, int]], rtl: bool) -> None:
        """Apply GPOS ``lookups`` to ``buf`` in place."""
        if self.gpos is None:
            return
        ctx = Applier(self.gpos, self.gdef, buf, parse_gpos, rtl)
        for index, mask in lookups:
            ctx.run(index, mask)

    def classify(self, info: Info) -> None:
        """Set ``info.gclass`` from GDEF, or from the Unicode category without GDEF."""
        cls = self.gdef.glyph_class(info.gid) if self.gdef.present else 0
        info.gclass = cls or synthetic_class(info.cp)


__all__ = ["ATTACH_CURSIVE", "ATTACH_MARK", "GLYPH_BASE", "GLYPH_LIGATURE", "GLYPH_MARK", "Info",
           "OpenTypeLayout", "synthetic_class"]
