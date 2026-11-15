"""From characters to shaped glyphs: bidi levels, script and font itemization, shaping and visual order."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ...dom.node import Node
from ...shaping._itemize import scripts
from ...shaping._shape import shape
from ...shaping.bidi import LTR, RTL, Paragraph, paragraph, reorder
from ._content import Char

LRE, RLE, LRO, RLO, PDF = "\u202a", "\u202b", "\u202d", "\u202e", "\u202c"
LRI, RLI, PDI = "\u2066", "\u2067", "\u2069"
RTL_DIRECTION = "rtl"
CLUSTER_CONTINUATION = frozenset({"Mn", "Me", "Mc", "Cf"})


def is_rtl(node: Node) -> bool:
    """Whether ``node``'s ``direction`` is right-to-left."""
    return node.style.get("direction", "ltr") == RTL_DIRECTION


def _opener(node: Node) -> tuple[str, str] | None:
    mode = node.style.get("unicode-bidi", "normal")
    rtl = is_rtl(node)
    if mode == "embed":
        return (RLE if rtl else LRE), PDF
    if mode == "bidi-override":
        return (RLO if rtl else LRO), PDF
    if mode == "isolate":
        return (RLI if rtl else LRI), PDI
    return None


class BidiText:
    """Resolved bidi levels for the characters of one ``text`` element."""

    def __init__(self, root: Node, chars: list[Char]):
        parts: list[str] = []
        self.positions: list[int] = []
        open_: list[tuple[Node, str]] = []
        for c in chars:
            chain = c.chain
            while open_ and open_[-1][0] not in chain:
                parts.append(open_.pop()[1])
            for node in chain:
                if any(node is n for n, _ in open_):
                    continue
                pair = _opener(node)
                if pair is not None:
                    parts.append(pair[0])
                    open_.append((node, pair[1]))
            self.positions.append(len(parts))
            parts.append(c.text)
        parts.extend(closer for _, closer in reversed(open_))
        self.text = "".join(parts)
        self.para: Paragraph = paragraph(self.text, RTL if is_rtl(root) else LTR)
        self.scripts = scripts("".join(c.text for c in chars))

    def line_levels(self, indices: list[int]) -> list[int]:
        """Levels of the characters ``indices`` (one chunk) after rule L1."""
        if not indices:
            return []
        lo, hi = self.positions[indices[0]], self.positions[indices[-1]] + 1
        levels = self.para.line_levels(lo, hi)
        return [levels[self.positions[i] - lo] for i in indices]

    def mirrored(self, i: int) -> str:
        """Character ``i``, mirrored when it resolves right-to-left."""
        return self.para.mirror(self.positions[i])


@dataclass
class RunGlyph:
    """A shaped glyph in a chunk, in visual order, offsets in user units (``y`` down)."""

    match: object
    gid: int
    index: int
    dx: float
    dy: float
    advance: float
    is_mark: bool


def _runs(chars: list[Char], indices: list[int], levels: list[int], bidi: BidiText, pick) -> list[tuple]:
    runs: list[list] = []
    for k, i in enumerate(indices):
        c = chars[i]
        if runs and unicodedata.category(c.text) in CLUSTER_CONTINUATION:
            match = runs[-1][1]
        else:
            match = pick(c.owner.style, c.text)
        key = (match.font, c.owner.font_size, bidi.scripts[i], levels[k], c.owner.style.get("kerning", "auto"))
        if runs and runs[-1][0] == key and runs[-1][1] is match:
            runs[-1][2].append(k)
        else:
            runs.append([key, match, [k]])
    return runs


def shape_chunk(chars: list[Char], indices: list[int], bidi: BidiText, pick, lang: str | None) -> list[RunGlyph]:
    """Shape the characters ``indices`` (one text chunk) into glyphs in visual order."""
    levels = bidi.line_levels(indices)
    visual = {k: v for v, k in enumerate(reorder(levels))}
    runs = _runs(chars, indices, levels, bidi, pick)
    runs.sort(key=lambda run: min(visual[k] for k in run[2]))
    out: list[RunGlyph] = []
    for (font, size, script, level, kerning), match, members in runs:
        text = "".join(bidi.mirrored(indices[k]) for k in members)
        s = size / font.units_per_em
        glyphs = shape(font, text, script, bool(level & 1), lang, kerning=kerning in ("auto", "inherit"))
        pen = 0.0
        for g in glyphs:
            k = members[min(g.cluster, len(members) - 1)]
            out.append(RunGlyph(match, g.gid, indices[k], (g.x - pen) * s, -g.y * s, g.advance * s, g.is_mark))
            pen += g.advance
    return out
