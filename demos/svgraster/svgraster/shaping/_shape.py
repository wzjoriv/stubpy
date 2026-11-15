"""Shaping one run (one font, script and direction) into positioned glyphs."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .ot import ATTACH_CURSIVE, ATTACH_MARK, GLYPH_MARK, Info, synthetic_class
from .shapers import Plan, Shaper, shaper_for

SCRIPT_TAGS = {
    "Arabic": [b"arab"], "Hebrew": [b"hebr"], "Syriac": [b"syrc"], "Thai": [b"thai"], "Lao": [b"lao "],
    "Devanagari": [b"dev2", b"deva"], "Bengali": [b"bng2", b"beng"], "Gurmukhi": [b"gur2", b"guru"],
    "Gujarati": [b"gjr2", b"gujr"], "Oriya": [b"ory2", b"orya"], "Tamil": [b"tml2", b"taml"],
    "Telugu": [b"tel2", b"telu"], "Kannada": [b"knd2", b"knda"], "Malayalam": [b"mlm2", b"mlym"],
    "Latin": [b"latn"], "Greek": [b"grek"], "Cyrillic": [b"cyrl"], "Armenian": [b"armn"],
    "Georgian": [b"geor"], "Han": [b"hani"], "Hiragana": [b"kana"], "Katakana": [b"kana"],
    "Hangul": [b"hang"], "Nko": [b"nko "],
}
LANG_TAGS = {
    "ar": b"ARA ", "fa": b"FAR ", "ur": b"URD ", "he": b"IWR ", "hi": b"HIN ", "mr": b"MAR ", "ne": b"NEP ",
    "sa": b"SAN ", "th": b"THA ", "en": b"ENG ", "de": b"DEU ", "fr": b"FRA ", "tr": b"TRK ", "ro": b"ROM ",
    "sr": b"SRB ", "ru": b"RUS ", "nl": b"NLD ", "pl": b"PLK ", "ja": b"JAN ", "zh": b"ZHS ", "ko": b"KOR ",
}
KERN = b"kern"
MARK_FEATURES = (b"mark", b"mkmk")


@dataclass
class ShapedGlyph:
    """A glyph of a shaped run in visual order; lengths are in font units, ``y`` up."""

    gid: int
    cluster: int
    x: float
    y: float
    advance: float
    is_mark: bool = False


def script_tags(script: str) -> list[bytes]:
    """OpenType script tags to try for an ISO script name."""
    return SCRIPT_TAGS.get(script, [script[:4].lower().encode("ascii", "replace").ljust(4)])


def lang_tag(lang: str | None) -> bytes | None:
    """The OpenType language system tag for a BCP 47 language (``None`` for the default)."""
    return LANG_TAGS.get(lang.split("-")[0].lower()) if lang else None


def _decompose(font, cp: int) -> list[int]:
    if font.glyph_index(chr(cp)):
        return [cp]
    parts = unicodedata.decomposition(chr(cp)).split()
    if not parts or parts[0].startswith("<"):
        return [cp]
    cps = [int(p, 16) for p in parts]
    expanded = [c for part in cps for c in _decompose(font, part)]
    return expanded if all(font.glyph_index(chr(c)) for c in expanded) else [cp]


def _buffer(font, cps: list[int], clusters: list[int], plan: Plan) -> list[Info]:
    buf = []
    for cp, cluster in zip(cps, clusters):
        for part in _decompose(font, cp):
            buf.append(Info(font.glyph_index(chr(part)), part, cluster, plan.global_mask))
    return buf


def _plain_buffer(font, text: str, plan: Plan) -> list[Info]:
    buf, i = [], 0
    for gid, consumed in font.map_text(text):
        info = Info(gid, ord(text[i]), i, plan.global_mask)
        info.gclass = synthetic_class(info.cp)
        buf.append(info)
        i += max(1, consumed)
    return buf


def shape(font, text: str, script: str = "Latin", rtl: bool = False, lang: str | None = None,
          vertical: bool = False, kerning: bool = True) -> list[ShapedGlyph]:
    """Shape ``text`` (logical order, already mirrored) and return glyphs in visual order."""
    shaper = shaper_for(script)
    layout = getattr(font, "layout", None)
    plan = Plan()
    if layout is None:
        buf = _plain_buffer(font, text, plan)
    else:
        cps, clusters = shaper.preprocess([ord(c) for c in text])
        buf = _buffer(font, cps, clusters, plan)
        for info in buf:
            layout.classify(info)
    if layout is not None:
        shaper.setup(buf, plan, font)
    gpos_lookups: list = []
    if layout is not None:
        tags, ltag = script_tags(script), lang_tag(lang)
        available = layout.features(layout.gsub, tags, ltag)
        for stage, features in enumerate(shaper.stages(vertical)):
            masks = {tag: plan.mask(tag) for tag in features}
            layout.substitute(buf, layout.lookups(available, masks), rtl)
            shaper.pause(stage, buf, plan, font)
        gpos_available = layout.features(layout.gpos, tags, ltag)
        gpos_lookups = layout.lookups(gpos_available, {tag: plan.mask(tag) for tag in shaper.positioning()
                                                         if kerning or tag != KERN})
    for info in buf:
        info.x_adv = font.advance(info.gid)
    if layout is not None:
        layout.position(buf, gpos_lookups, rtl)
    has_kern = layout is not None and any(layout.features(layout.gpos, script_tags(script), None).get(KERN, ()))
    has_marks = layout is not None and any(layout.features(layout.gpos, script_tags(script), None).get(t)
                                           for t in MARK_FEATURES)
    if shaper.zero_marks:
        for info in buf:
            if info.gclass == GLYPH_MARK and info.attach_kind != ATTACH_CURSIVE:
                info.x_adv = 0
    order = list(range(len(buf)))[::-1] if rtl else list(range(len(buf)))
    if kerning and not has_kern:
        _legacy_kern(font, buf, order)
    if not has_marks and shaper.fallback_marks:
        _fallback_marks(font, buf)
    return _place(buf, order)


def _legacy_kern(font, buf: list[Info], order: list[int]) -> None:
    prev = None
    for i in order:
        if buf[i].gclass == GLYPH_MARK:
            continue
        if prev is not None:
            buf[prev].x_adv += font.kern(buf[prev].gid, buf[i].gid)
        prev = i


def _fallback_marks(font, buf: list[Info]) -> None:
    extents = getattr(font, "glyph_extents", None)
    if extents is None:
        return
    base = -1
    for i, info in enumerate(buf):
        if info.gclass != GLYPH_MARK:
            base = i
            continue
        if base < 0 or info.attach >= 0 or info.x_adv:
            continue
        b, m = extents(buf[base].gid), extents(info.gid)
        if b is None or m is None:
            continue
        info.attach, info.attach_kind = base, ATTACH_MARK
        info.x_off = (b[0] + b[2]) / 2 - (m[0] + m[2]) / 2
        info.y_off = 0


def _place(buf: list[Info], order: list[int]) -> list[ShapedGlyph]:
    origin = [0.0] * len(buf)
    pen = 0.0
    for i in order:
        origin[i] = pen
        pen += buf[i].x_adv
    done: dict[int, tuple[float, float]] = {}

    def where(i: int, depth: int = 0) -> tuple[float, float]:
        if i in done:
            return done[i]
        info = buf[i]
        parent = info.attach
        if 0 <= parent < len(buf) and parent != i and depth < len(buf):
            px, py = where(parent, depth + 1)
            if info.attach_kind == ATTACH_MARK:
                found = (px + info.x_off, py + info.y_off)
            else:
                found = (origin[i] + info.x_off, py + info.y_off)
        else:
            found = (origin[i] + info.x_off, float(info.y_off))
        done[i] = found
        return found

    out = []
    for i in order:
        x, y = where(i)
        info = buf[i]
        out.append(ShapedGlyph(info.gid, info.cluster, x, y, float(info.x_adv), info.gclass == GLYPH_MARK))
    return out
