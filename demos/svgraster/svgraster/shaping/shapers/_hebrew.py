"""Hebrew shaping: marks positioned by GPOS, or composed into presentation forms, or centred as a fallback."""
from __future__ import annotations

import unicodedata

from ._base import Shaper

PRESENTATION_START, PRESENTATION_END = 0xFB1D, 0xFB4F
_compositions: dict[tuple[int, int], int] = {}


def compose(base: int, mark: int) -> int | None:
    """The Alphabetic Presentation Forms character for ``base`` + ``mark``, if any."""
    if not _compositions:
        for p in range(PRESENTATION_START, PRESENTATION_END + 1):
            parts = unicodedata.decomposition(chr(p)).split()
            if len(parts) == 2 and not parts[0].startswith("<"):
                _compositions[(int(parts[0], 16), int(parts[1], 16))] = p
    return _compositions.get((base, mark))


class HebrewShaper(Shaper):
    """Hebrew: when the font cannot position marks, compose base and mark into presentation forms."""

    def setup(self, buf, plan, font) -> None:
        layout = font.layout
        if layout is not None and layout.gpos is not None:
            return
        i = 1
        while i < len(buf):
            prev, info = buf[i - 1], buf[i]
            composed = compose(prev.cp, info.cp)
            gid = font.glyph_index(chr(composed)) if composed is not None else 0
            if gid:
                prev.gid, prev.cp = gid, composed
                del buf[i]
                continue
            i += 1
