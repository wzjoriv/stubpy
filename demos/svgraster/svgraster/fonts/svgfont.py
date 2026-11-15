"""SVG fonts (``font``, ``font-face``, ``glyph``, ``missing-glyph``, ``hkern``) as font faces."""
from __future__ import annotations

import math

import numpy as np

from ..dom.transform import Matrix
from ..parse.flatten import flatten_path
from ..parse.pathdata import Path, PathSyntaxError, parse_path
from ._tables import Metrics, Naming
from .database import weight_value

DEFAULT_UNITS_PER_EM = 1000
MISSING = 0


def _float(node, name: str, default: float) -> float:
    try:
        return float(node.get(name, default))
    except (TypeError, ValueError):
        return default


def _path(d: str | None) -> Path:
    try:
        return parse_path(d or "")
    except PathSyntaxError:
        return Path()


class SvgFont:
    """A face built from an SVG ``font`` element, with ligatures by longest match."""

    outline_format = "svg"

    def __init__(self, node):
        face = next((c for c in node.children if c.tag == "font-face"), None)
        attrs = face if face is not None else node
        upm = _float(attrs, "units-per-em", DEFAULT_UNITS_PER_EM) or DEFAULT_UNITS_PER_EM
        self.metrics = m = Metrics(units_per_em=int(upm))
        m.ascent = int(_float(attrs, "ascent", upm * 0.8))
        m.descent = -abs(int(_float(attrs, "descent", upm * 0.2)))
        m.x_height = int(_float(attrs, "x-height", upm * 0.5))
        m.cap_height = int(_float(attrs, "cap-height", upm * 0.7))
        m.underline_position = int(_float(attrs, "underline-position", -upm * 0.1))
        m.underline_thickness = int(_float(attrs, "underline-thickness", upm * 0.05))
        m.strikeout_position = int(_float(attrs, "strikethrough-position", upm * 0.3))
        m.strikeout_size = int(_float(attrs, "strikethrough-thickness", upm * 0.05))
        family = (attrs.get("font-family") or node.get("id") or "").strip("'\" ")
        style = (attrs.get("font-style") or "normal").lower()
        self.naming = Naming(family=family, weight=weight_value(attrs.get("font-weight")),
                             italic=style in ("italic", "oblique"), aliases={family.lower()})
        default_adv = _float(node, "horiz-adv-x", upm / 2)
        missing = next((c for c in node.children if c.tag == "missing-glyph"), None)
        self._paths = [_path(missing.get("d")) if missing is not None else Path()]
        self._advances = [_float(missing, "horiz-adv-x", default_adv) if missing is not None else default_adv]
        self._by_text: dict[str, int] = {}
        self._by_name: dict[str, int] = {}
        for child in node.children:
            if child.tag != "glyph":
                continue
            gid = len(self._paths)
            self._paths.append(_path(child.get("d")))
            self._advances.append(_float(child, "horiz-adv-x", default_adv))
            text = child.get("unicode")
            if text and text not in self._by_text:
                self._by_text[text] = gid
            name = child.get("glyph-name")
            if name:
                for n in name.split(","):
                    self._by_name.setdefault(n.strip(), gid)
        self._max_len = max((len(t) for t in self._by_text), default=1)
        self._kerns: dict[tuple[int, int], float] = {}
        for child in node.children:
            if child.tag == "hkern":
                self._add_kern(child)
        self._polys: dict[tuple[int, int], list[np.ndarray]] = {}

    def _glyph_set(self, unicodes: str | None, names: str | None) -> set[int]:
        out = set()
        for u in (unicodes or "").split(","):
            u = u.strip()
            if u in self._by_text:
                out.add(self._by_text[u])
        for n in (names or "").split(","):
            if n.strip() in self._by_name:
                out.add(self._by_name[n.strip()])
        return out

    def _add_kern(self, node) -> None:
        k = _float(node, "k", 0.0)
        for a in self._glyph_set(node.get("u1"), node.get("g1")):
            for b in self._glyph_set(node.get("u2"), node.get("g2")):
                self._kerns.setdefault((a, b), -k)

    def __repr__(self) -> str:
        return f"<SvgFont {self.family!r} {len(self._paths) - 1} glyphs>"

    family = property(lambda self: self.naming.family, doc="The family name.")
    weight = property(lambda self: self.naming.weight, doc="The CSS weight.")
    italic = property(lambda self: self.naming.italic, doc="Whether the face is italic.")
    units_per_em = property(lambda self: self.metrics.units_per_em, doc="Font units per em.")

    def map_text(self, text: str) -> list[tuple[int, int]]:
        """``(glyph id, characters consumed)`` pairs, preferring the longest ``unicode`` match."""
        out, i = [], 0
        while i < len(text):
            for n in range(min(self._max_len, len(text) - i), 0, -1):
                gid = self._by_text.get(text[i:i + n])
                if gid is not None:
                    out.append((gid, n))
                    i += n
                    break
            else:
                out.append((MISSING, 1))
                i += 1
        return out

    def glyph_index(self, char: str) -> int:
        """The glyph for a single character, 0 when missing."""
        return self._by_text.get(char, MISSING)

    def has_glyph(self, char: str) -> bool:
        """Whether ``char`` has a ``glyph``."""
        return char in self._by_text

    def advance(self, gid: int) -> float:
        """Advance in font units."""
        return self._advances[gid] if 0 <= gid < len(self._advances) else 0.0

    def kern(self, left: int, right: int) -> float:
        """``hkern`` adjustment in font units."""
        return self._kerns.get((left, right), 0.0)

    def outline(self, gid: int) -> Path:
        """The glyph path in font units (y up)."""
        return self._paths[gid] if 0 <= gid < len(self._paths) else Path()

    def glyph_polygons(self, gid: int, to_user: Matrix, tolerance: float) -> list[np.ndarray]:
        """Flattened glyph contours mapped by ``to_user``."""
        scale = to_user.mean_scale or 1.0
        bucket = int(math.floor(math.log2(max(tolerance / scale, 1e-6))))
        key = (gid, bucket)
        if key not in self._polys:
            self._polys[key] = [p.points for p in flatten_path(self.outline(gid), 2.0 ** bucket) if len(p.points) > 2]
        return [to_user.apply_points(p) for p in self._polys[key]]
