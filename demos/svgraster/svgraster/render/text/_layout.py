"""Glyph placement: chunks in visual order, anchors, spacing, baselines, rotation, ``textLength`` and vertical text."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import numpy as np

from ...dom.node import Node
from ...dom.transform import Matrix
from ...dom.units import parse_length
from ._baseline import baseline_offset, baseline_shift, pick, spacing
from ._content import Char, collect
from ._runs import BidiText, RunGlyph, is_rtl, shape_chunk
from ._textpath import PathMeasure

OBLIQUE_DEGREES = 12.0
VERTICAL_MODES = frozenset({"tb", "tb-rl", "tb-lr", "vertical-rl", "vertical-lr"})
UPRIGHT_WIDTHS = frozenset({"W", "F"})
SIDEWAYS = 90.0


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


def _lang(node: Node) -> str | None:
    while node is not None:
        lang = node.attrs.get("lang")
        if lang:
            return lang
        node = node.parent
    return None


def _orientation(owner: Node, ch: str) -> float:
    value = owner.style.get("glyph-orientation-vertical", "auto").strip()
    if value == "auto":
        return 0.0 if unicodedata.east_asian_width(ch) in UPRIGHT_WIDTHS else SIDEWAYS
    try:
        return float(value.removesuffix("deg")) % 360.0
    except ValueError:
        return 0.0


class TextLayout:
    """Lays out one ``text`` element; :attr:`glyphs` are in user space."""

    def __init__(self, node: Node, viewport, fonts, document=None):
        self.node = node
        self.viewport = viewport
        self.fonts = fonts
        self.chars = collect(node, viewport, document)
        self.document = document
        self.bidi = BidiText(node, self.chars)
        self.lang = _lang(node)
        self.vertical = node.style.get("writing-mode", "lr-tb") in VERTICAL_MODES
        self.glyphs: list[Glyph] = []
        self.chunks: list[tuple[int, int, str, bool, float]] = []
        self._place()

    def _pick(self, style, ch: str):
        return pick(self.fonts, style, ch)

    def _segments(self):
        chars, current, path = self.chars, [], None
        for i, c in enumerate(chars):
            starts = c.path is not path or (c.path is None and i > 0 and (c.x is not None or c.y is not None))
            if current and starts:
                yield path, current
                current = []
            path = c.path
            current.append(i)
        if current:
            yield path, current

    def _place(self) -> None:
        x = y = 0.0
        for path, indices in self._segments():
            if path is not None:
                x, y = self._path_run(indices, x, y)
                continue
            c = self.chars[indices[0]]
            x = c.x if c.x is not None else x
            y = c.y if c.y is not None else y
            x, y = (self._vertical_chunk if self.vertical else self._chunk)(indices, x, y)
        self._text_length()
        self._anchor()

    def _shaped(self, indices: list[int]) -> list[RunGlyph]:
        return shape_chunk(self.chars, indices, self.bidi, self._pick, self.lang)

    def _make(self, rg: RunGlyph, x: float, y: float) -> Glyph:
        c = self.chars[rg.index]
        owner, font = c.owner, rg.match.font
        y += baseline_offset(owner, font, owner.font_size) - baseline_shift(c.chain, self.viewport)
        return Glyph(font, rg.gid, c, x, y, owner.font_size, rg.advance, rotate=c.rotate or 0.0,
                     oblique=rg.match.synthetic_oblique, synthetic_bold=rg.match.synthetic_bold,
                     chunk=len(self.chunks))

    def _after(self, c: Char) -> float:
        owner = c.owner
        extra = spacing(owner, "letter-spacing", self.viewport)
        kerning = owner.style.get("kerning", "auto")
        if kerning not in ("auto", "inherit"):
            extra += parse_length(kerning, owner.units(self.viewport), "x", 0.0)
        if c.text == " ":
            extra += spacing(owner, "word-spacing", self.viewport)
        return extra

    def _dx_shifts(self, shaped: list[RunGlyph], rtl: bool) -> list[float]:
        """Cumulative ``dx`` per glyph, accumulated in logical order (right to left for RTL)."""
        out = [0.0] * len(shaped)
        acc, seen = 0.0, set()
        order = range(len(shaped) - 1, -1, -1) if rtl else range(len(shaped))
        for k in order:
            rg = shaped[k]
            if rg.index not in seen and not rg.is_mark:
                acc += self.chars[rg.index].dx
                seen.add(rg.index)
            out[k] = acc
        return out

    def _dy(self, indices: list[int]) -> dict[int, float]:
        out, acc = {}, 0.0
        for i in indices:
            acc += self.chars[i].dy
            out[i] = acc
        return out

    def _chunk(self, indices: list[int], x: float, y: float) -> tuple[float, float]:
        dys = self._dy(indices)
        start = len(self.glyphs)
        rtl = is_rtl(self.chars[indices[0]].owner)
        shaped = self._shaped(indices)
        moves = self._dx_shifts(shaped, rtl)
        pen = shift = pending = 0.0
        for rg, move in zip(shaped, moves):
            c = self.chars[rg.index]
            if not rg.is_mark:
                shift += pending
                pending = self._after(c)
            self.glyphs.append(self._make(rg, x + pen + shift + move + rg.dx, y + dys[rg.index] + rg.dy))
            pen += rg.advance
        width = pen + shift + pending
        if rtl:
            for g in self.glyphs[start:]:
                g.x -= width
        else:
            width += moves[-1] if moves else 0.0
        self._close_chunk(start, rtl, width)
        return (x - width if rtl else x + width), y + dys[indices[-1]]

    def _vertical_chunk(self, indices: list[int], x: float, y: float) -> tuple[float, float]:
        start = len(self.glyphs)
        pen, dx = 0.0, 0.0
        seen: set[int] = set()
        for rg in self._shaped(indices):
            c = self.chars[rg.index]
            font, size = rg.match.font, c.owner.font_size
            s = size / font.units_per_em
            if rg.index not in seen and not rg.is_mark:
                pen += c.dy
                dx += c.dx
            seen.add(rg.index)
            angle = _orientation(c.owner, c.text)
            m = font.metrics
            if angle == SIDEWAYS:
                gx, gy, step = x + dx - (m.ascent + m.descent) / 2 * s, y + pen + rg.dx, rg.advance
            else:
                vadv = font.vertical_advance(rg.gid) if hasattr(font, "vertical_advance") else m.ascent - m.descent
                gx, gy, step = x + dx - rg.advance / 2 + rg.dx, y + pen + m.ascent * s + rg.dy, vadv * s
            glyph = self._make(rg, gx, gy)
            glyph.y = gy
            glyph.angle = angle
            self.glyphs.append(glyph)
            if not rg.is_mark:
                pen += step + self._after(c)
        self._close_chunk(start, False, pen, vertical=True)
        return x + dx, y + pen

    def _close_chunk(self, start: int, rtl: bool, length: float, vertical: bool = False) -> None:
        if start >= len(self.glyphs):
            return
        first = self.glyphs[start].char
        anchor = first.owner.style.get("text-anchor", "start")
        self.chunks.append((start, len(self.glyphs), anchor, rtl, length if vertical else -1.0))

    def _text_length(self) -> None:
        for node in self.node.iter():
            raw = node.get("textLength")
            if raw is None or node.tag not in ("text", "tspan", "textPath") or self.vertical:
                continue
            target = parse_length(raw, node.units(self.viewport), "x", -1.0)
            mine = sorted((g for g in self.glyphs if node in g.char.chain and not g.on_path), key=lambda g: g.x)
            if target < 0 or not mine:
                continue
            x0 = mine[0].x
            actual = max(g.x + g.advance for g in mine) - x0
            if actual <= 0:
                continue
            last = max(self.glyphs.index(g) for g in mine)
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
        for start, end, anchor, rtl, length in self.chunks:
            if anchor not in ("middle", "end"):
                continue
            run = [g for g in self.glyphs[start:end] if not g.on_path]
            if not run:
                continue
            if length >= 0:
                shift = length / 2.0 if anchor == "middle" else length
                for g in run:
                    g.y -= shift
                continue
            width = max(g.x + g.advance for g in run) - min(g.x for g in run)
            shift = width / 2.0 if anchor == "middle" else width
            for g in run:
                g.x += shift if rtl else -shift

    def _path_run(self, indices: list[int], x: float, y: float) -> tuple[float, float]:
        text_path = self.chars[indices[0]].path
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
        u = v = pending = 0.0
        seen: set[int] = set()
        for rg in self._shaped(indices):
            c = self.chars[rg.index]
            if rg.index not in seen and not rg.is_mark:
                u = (c.x - start) if c.x is not None else u + pending
                u, v = u + c.dx, v + c.dy
                pending = self._after(c)
            seen.add(rg.index)
            glyph = self._make(rg, 0.0, rg.dy)
            placed.append((glyph, u + rg.dx, v))
            u += rg.advance
        anchor = text_path.style.get("text-anchor", "start")
        total = u + pending
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
        self.chunks.append((len(self.glyphs), len(self.glyphs), "start", False, -1.0))
        end = measure.at(min(measure.length, offset + total)) or (x, y, 0.0)
        return end[0], end[1]

    def bounds(self) -> tuple[float, float, float, float] | None:
        """Union of the visible glyph cells, ``(x0, y0, x1, y1)``."""
        cells = [g.cell() for g in self.glyphs if g.visible]
        if not cells:
            return None
        pts = np.concatenate(cells)
        return (float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max()))
