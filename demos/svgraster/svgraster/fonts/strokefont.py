"""The built-in single-stroke font as a face; the last resort when no outline font has a glyph."""
from __future__ import annotations

import numpy as np

from ..dom.transform import Matrix
from ..raster.stroke import stroke_polylines
from ._strokeglyphs import ADVANCE, GLYPHS, GRID_HEIGHT, LOWERCASE_SCALE, glyph
from ._tables import Metrics, Naming

CAP_HEIGHT_EM = 0.7
STROKE_EM = 0.1
BOLD_STROKE_EM = 0.15
BOLD_THRESHOLD = 600
UNITS_PER_EM = GRID_HEIGHT / CAP_HEIGHT_EM
STROKE_JOIN = "round"


class StrokeFont:
    """Covers A-Z, 0-9 and common punctuation; lowercase is drawn as small capitals."""

    outline_format = "stroke"

    def __init__(self, weight: int = 400):
        upm = UNITS_PER_EM
        self.metrics = Metrics(units_per_em=upm, ascent=0.8 * upm, descent=-0.2 * upm,
                               x_height=GRID_HEIGHT * LOWERCASE_SCALE, cap_height=GRID_HEIGHT,
                               underline_position=-0.1 * upm, underline_thickness=0.05 * upm,
                               strikeout_position=0.3 * upm, strikeout_size=0.05 * upm)
        self.naming = Naming(family="svgraster stroke", weight=weight)
        self.stroke_width = (BOLD_STROKE_EM if weight >= BOLD_THRESHOLD else STROKE_EM) * upm
        self._chars: list[str] = ["\0"]
        self._ids: dict[str, int] = {}

    def __repr__(self) -> str:
        return f"<StrokeFont weight={self.weight}>"

    family = property(lambda self: self.naming.family, doc="The family name.")
    weight = property(lambda self: self.naming.weight, doc="The CSS weight.")
    italic = property(lambda self: False, doc="Never italic.")
    units_per_em = property(lambda self: self.metrics.units_per_em, doc="Font units per em.")

    def glyph_index(self, char: str) -> int:
        """A stable id per character (every character gets one; unknown ones draw a box)."""
        gid = self._ids.get(char)
        if gid is None:
            gid = self._ids[char] = len(self._chars)
            self._chars.append(char)
        return gid

    def has_glyph(self, char: str) -> bool:
        """Whether the character has a real stroke glyph."""
        return char in GLYPHS or char.upper() in GLYPHS

    def map_text(self, text: str) -> list[tuple[int, int]]:
        """One glyph per character."""
        return [(self.glyph_index(ch), 1) for ch in text]

    def advance(self, gid: int) -> float:
        """Advance in grid units."""
        return glyph(self._chars[gid])[1] if 0 < gid < len(self._chars) else ADVANCE

    def kern(self, left: int, right: int) -> float:
        """No kerning."""
        return 0.0

    def glyph_polygons(self, gid: int, to_user: Matrix, tolerance: float) -> list[np.ndarray]:
        """Stroke outlines of the glyph mapped by ``to_user``."""
        if not 0 < gid < len(self._chars):
            return []
        strokes, _ = glyph(self._chars[gid])
        flipped = [(s * (1.0, -1.0), False) for s in strokes]
        tol = tolerance / (to_user.mean_scale or 1.0)
        outline = stroke_polylines(flipped, self.stroke_width, STROKE_JOIN, STROKE_JOIN, tolerance=tol)
        return [to_user.apply_points(p) for p in outline]
