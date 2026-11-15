"""Glyph placement: chunks, anchors, spacing, kerning, baselines, rotation and ``textLength``."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...dom.node import Node
from ...dom.transform import Matrix
from ...dom.units import parse_length
from ._content import Char, collect
from ._textpath import PathMeasure

OBLIQUE_DEGREES = 12.0
MAX_LIGATURE = 8
SUPER_EM = 1.0 / 3.0
SUB_EM = -0.2
DEFAULT_X_HEIGHT_EM = 0.5
HANGING_ASCENT = 0.8
MATH_ASCENT = 0.5
EDGE_BASELINES = {"text-before-edge": "ascent", "text-top": "ascent", "before-edge": "ascent",
                  "text-after-edge": "descent", "text-bottom": "descent", "after-edge": "descent",
                  "ideographic": "descent"}


@dataclass
class Glyph:
    """A positioned glyph; ``matrix`` maps font units (y up) to user space."""

    font: object
    gid: int
    char: Char
    x: float
    y: float
    size: float
    advance: float
    rotate: float = 0.0
    hscale: float = 1.0
    oblique: bool = False
    synthetic_bold: bool = False
    chunk: int = 0
    angle: float = 0.0
    on_path: bool = False
    visible: bool = True

    @property
    def owner(self) -> Node:
        """The element whose style paints this glyph."""
        return self.char.owner

    @property
    def matrix(self) -> Matrix:
        """Font units to user space."""
        s = self.size / self.font.units_per_em
        m = Matrix.translate(self.x, self.y) @ Matrix.rotate(self.angle + self.rotate)
        if self.oblique:
            m = m @ Matrix.skew_x(-OBLIQUE_DEGREES)
        return m @ Matrix.scale(s * self.hscale, -s)

    def cell(self) -> np.ndarray:
        """The glyph cell (advance by ascent to descent) as four user-space points."""
        f = self.font
        adv = self.advance / (self.size / f.units_per_em) / self.hscale
        m = f.metrics
        return self.matrix.apply_points(np.array([[0, m.descent], [adv, m.descent], [adv, m.ascent], [0, m.ascent]],
                                                 dtype=np.float64))


def _spacing(node: Node, prop: str, viewport) -> float:
    value = node.style.get(prop, "normal")
    if value in ("normal", "auto"):
        return 0.0
    return parse_length(value, node.units(viewport), "x", 0.0)


def _baseline_shift(chain: tuple[Node, ...], viewport) -> float:
    total = 0.0
    for node in chain[1:]:
        value = node.specified.get("baseline-shift", "baseline").strip()
        if value == "baseline":
            continue
        if value == "super":
            total += node.font_size * SUPER_EM
        elif value == "sub":
            total += node.font_size * SUB_EM
        elif value.endswith("%"):
            total += node.font_size * float(value[:-1]) / 100.0
        else:
            total += parse_length(value, node.units(viewport), "y", 0.0)
    return total


def _baseline_offset(owner: Node, font, size: float) -> float:
    key = owner.style.get("alignment-baseline", "auto")
    if key in ("auto", "baseline", "inherit"):
        key = owner.style.get("dominant-baseline", "auto")
    m = font.metrics
    s = size / font.units_per_em
    if key in ("middle",):
        return (m.x_height or DEFAULT_X_HEIGHT_EM * font.units_per_em) / 2 * s
    if key in ("central",):
        return (m.ascent + m.descent) / 2 * s
    if key == "hanging":
        return HANGING_ASCENT * m.ascent * s
    if key == "mathematical":
        return MATH_ASCENT * m.ascent * s
    if key in EDGE_BASELINES:
        return (m.ascent if EDGE_BASELINES[key] == "ascent" else m.descent) * s
    return 0.0


def _pick(fonts, style, ch: str):
    matches = fonts.matches(style)
    for match in matches:
        if ch.isspace() or match.font.has_glyph(ch):
            return match
    return fonts.fallback(ch, style) or matches[-1]


class TextLayout:
    """Lays out one ``text`` element; :attr:`glyphs` are in user space."""

    def __init__(self, node: Node, viewport, fonts, document=None):
        self.node = node
        self.viewport = viewport
        self.fonts = fonts
        self.chars = collect(node, viewport, document)
        self.document = document
        self.glyphs: list[Glyph] = []
        self.chunks: list[tuple[int, int, str]] = []
        self._place()

    def _place(self) -> None:
        chars = self.chars
        x = y = 0.0
        i = 0
        prev: Glyph | None = None
        chunk_start = 0
        while i < len(chars):
            c = chars[i]
            if c.path is not None:
                run = [k for k in range(i, len(chars)) if chars[k].path is c.path]
                self._close_chunk(chunk_start)
                x, y = self._path_run(chars[i:run[-1] + 1], x, y)
                i = run[-1] + 1
                chunk_start, prev = len(self.glyphs), None
                continue
            if i > 0 and (c.x is not None or c.y is not None):
                self._close_chunk(chunk_start)
                chunk_start, prev = len(self.glyphs), None
            x = c.x if c.x is not None else x
            y = c.y if c.y is not None else y
            x, y = x + c.dx, y + c.dy
            glyph, consumed = self._glyph(chars, i, x, y, prev)
            self.glyphs.append(glyph)
            x += glyph.advance + self._after(glyph)
            prev = glyph
            i += consumed
        self._close_chunk(chunk_start)
        self._text_length()
        self._anchor()

    def _glyph(self, chars: list[Char], i: int, x: float, y: float, prev: Glyph | None) -> tuple[Glyph, int]:
        c = chars[i]
        owner = c.owner
        match = _pick(self.fonts, owner.style, c.text)
        font, size = match.font, owner.font_size
        run = c.text
        for ch in chars[i + 1:i + MAX_LIGATURE]:
            if ch.owner is not owner or ch.x is not None or ch.y is not None or ch.dx or ch.dy or ch.rotate:
                break
            run += ch.text
        gid, consumed = font.map_text(run)[0]
        consumed = max(1, consumed)
        s = size / font.units_per_em
        if (prev is not None and prev.font is font and c.x is None and c.dx == 0
                and owner.style.get("kerning", "auto") == "auto"):
            x += font.kern(prev.gid, gid) * s
        shift = _baseline_shift(c.chain, self.viewport)
        y_base = y - shift + _baseline_offset(owner, font, size)
        glyph = Glyph(font, gid, c, x, y_base, size, font.advance(gid) * s, rotate=c.rotate or 0.0,
                      oblique=match.synthetic_oblique, synthetic_bold=match.synthetic_bold,
                      chunk=len(self.chunks))
        return glyph, consumed

    def _after(self, glyph: Glyph) -> float:
        owner = glyph.owner
        extra = _spacing(owner, "letter-spacing", self.viewport)
        kerning = owner.style.get("kerning", "auto")
        if kerning not in ("auto", "inherit"):
            extra += parse_length(kerning, owner.units(self.viewport), "x", 0.0)
        if glyph.char.text == " ":
            extra += _spacing(owner, "word-spacing", self.viewport)
        return extra

    def _close_chunk(self, start: int) -> None:
        if start >= len(self.glyphs):
            return
        first = self.glyphs[start].char
        anchor = first.owner.style.get("text-anchor", "start")
        self.chunks.append((start, len(self.glyphs), anchor))
        for g in self.glyphs[start:]:
            g.chunk = len(self.chunks) - 1

    def _text_length(self) -> None:
        for node in self.node.iter():
            raw = node.get("textLength")
            if raw is None or node.tag not in ("text", "tspan", "textPath"):
                continue
            target = parse_length(raw, node.units(self.viewport), "x", -1.0)
            mine = [g for g in self.glyphs if node in g.char.chain and not g.on_path]
            if target < 0 or not mine:
                continue
            x0 = mine[0].x
            actual = mine[-1].x + mine[-1].advance - x0
            if actual <= 0:
                continue
            last = self.glyphs.index(mine[-1])
            if node.get("lengthAdjust", "spacing") == "spacingAndGlyphs":
                k = target / actual
                for g in mine:
                    g.x = x0 + (g.x - x0) * k
                    g.hscale *= k
                    g.advance *= k
            else:
                gap = (target - actual) / max(1, len(mine) - 1)
                for n, g in enumerate(mine):
                    g.x += n * gap
            delta = target - actual
            for g in self.glyphs[last + 1:]:
                if g.chunk == mine[-1].chunk:
                    g.x += delta

    def _anchor(self) -> None:
        for start, end, anchor in self.chunks:
            if anchor not in ("middle", "end"):
                continue
            run = [g for g in self.glyphs[start:end] if not g.on_path]
            if not run:
                continue
            width = max(g.x + g.advance for g in run) - min(g.x for g in run)
            shift = width / 2.0 if anchor == "middle" else width
            for g in run:
                g.x -= shift

    def _path_run(self, chars: list[Char], x: float, y: float) -> tuple[float, float]:
        text_path = chars[0].path
        ref = self.document.lookup(text_path.href) if self.document is not None else None
        if ref is None or ref.tag not in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon"):
            return x, y
        measure = PathMeasure(ref, self.viewport)
        raw = text_path.get("startOffset", "0")
        if raw.strip().endswith("%"):
            start = measure.length * float(raw.strip()[:-1]) / 100.0
        else:
            start = parse_length(raw, text_path.units(self.viewport), "x", 0.0)
        placed: list[tuple[Glyph, float, float]] = []
        u, v, prev, i = 0.0, 0.0, None, 0
        while i < len(chars):
            c = chars[i]
            u = (c.x - start) if c.x is not None else u
            u, v = u + c.dx, v + c.dy
            glyph, consumed = self._glyph(chars, i, 0.0, 0.0, prev)
            placed.append((glyph, u, v))
            u += glyph.advance + self._after(glyph)
            prev = glyph
            i += consumed
        anchor = text_path.style.get("text-anchor", "start")
        total = u
        offset = start - (total / 2.0 if anchor == "middle" else total if anchor == "end" else 0.0)
        chunk = len(self.chunks)
        for glyph, gu, gv in placed:
            mid = offset + gu + glyph.advance / 2.0
            where = measure.at(mid)
            glyph.chunk = chunk
            glyph.on_path = True
            if where is None:
                glyph.visible = False
                continue
            px, py, angle = where
            rad = np.radians(angle)
            normal = (-np.sin(rad), np.cos(rad))
            dy = gv + glyph.y
            glyph.x = px - np.cos(rad) * glyph.advance / 2.0 + normal[0] * dy
            glyph.y = py - np.sin(rad) * glyph.advance / 2.0 + normal[1] * dy
            glyph.angle = angle
            self.glyphs.append(glyph)
        self.chunks.append((len(self.glyphs), len(self.glyphs), "start"))
        end = measure.at(min(measure.length, offset + total)) or (x, y, 0.0)
        return end[0], end[1]

    def bounds(self) -> tuple[float, float, float, float] | None:
        """Union of the visible glyph cells, ``(x0, y0, x1, y1)``."""
        cells = [g.cell() for g in self.glyphs if g.visible]
        if not cells:
            return None
        pts = np.concatenate(cells)
        return (float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max()))
