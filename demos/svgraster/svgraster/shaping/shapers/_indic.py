"""Indic (Devanagari) shaping: syllables, base consonants, reph and pre-base matra reordering."""
from __future__ import annotations

from .._ucd import INDIC_POSITIONAL, INDIC_SYLLABIC
from ._base import COMMON_STAGES, Plan, Shaper

OTHER, C, V, M, H, N, SM, ZWJ, ZWNJ = range(9)
POS_REPH, POS_PRE_M, POS_PRE_C, POS_BASE, POS_POST_C, POS_MATRA, POS_SMVD = range(1, 8)
CATEGORIES = {
    "Consonant": C, "Consonant_Dead": C, "Consonant_With_Stacker": C, "Consonant_Placeholder": C,
    "Consonant_Preceding_Repha": C, "Consonant_Prefixed": C,
    "Vowel_Independent": V, "Vowel_Dependent": M, "Virama": H, "Invisible_Stacker": H, "Nukta": N,
    "Bindu": SM, "Visarga": SM, "Cantillation_Mark": SM, "Tone_Mark": SM, "Syllable_Modifier": SM,
    "Joiner": ZWJ, "Non_Joiner": ZWNJ,
}
JOINERS = frozenset({ZWJ, ZWNJ})
RA = frozenset({0x0930})
PRE_BASE_POSITION = "Left"
BASIC = (b"nukt", b"akhn", b"rphf", b"rkrf", b"pref", b"blwf", b"abvf", b"half", b"pstf", b"vatu", b"cjct")
PRESENTATION = (b"init", b"pres", b"abvs", b"blws", b"psts", b"haln", b"calt", b"clig", b"liga", b"rclt")
LOCAL = (b"rphf", b"half", b"blwf", b"pstf", b"abvf", b"pref")
FINAL_STAGE = len(COMMON_STAGES) + len(BASIC) - 1


def category(cp: int) -> int:
    """The Indic syllabic category of ``cp`` as one of the module's constants."""
    return CATEGORIES.get(INDIC_SYLLABIC.get(cp, ""), OTHER)


def syllables(cats: list[int]) -> list[tuple[int, int]]:
    """``(start, end)`` of each syllable (consonant, vowel, or a lone character)."""
    out, i, n = [], 0, len(cats)
    while i < n:
        start = i
        if cats[i] in (C, V):
            first = cats[i]
            i += 1
            while True:
                if i < n and cats[i] == N:
                    i += 1
                if first == C and i < n and cats[i] == H:
                    i += 1
                    if i < n and cats[i] in JOINERS:
                        i += 1
                    if i < n and cats[i] == C:
                        i += 1
                        continue
                    break
                while i < n and cats[i] in (M, N, H, ZWJ):
                    i += 1
                break
            while i < n and cats[i] == SM:
                i += 1
        else:
            i += 1
        out.append((start, i))
    return out


class IndicShaper(Shaper):
    """Devanagari after the OpenType "dev2" model."""

    zero_marks = False

    def stages(self, vertical: bool = False) -> list[tuple[bytes, ...]]:
        return [*COMMON_STAGES, *((f,) for f in BASIC), PRESENTATION]

    def setup(self, buf, plan: Plan, font) -> None:
        for tag in LOCAL:
            plan.mask(tag, global_=False)
        for info in buf:
            info.cat = category(info.cp)
        for n, (start, end) in enumerate(syllables([info.cat for info in buf])):
            for info in buf[start:end]:
                info.syllable = n + 1
            if buf[start].cat == C:
                self._consonant_syllable(buf, start, end, plan)

    def _consonant_syllable(self, buf, start: int, end: int, plan: Plan) -> None:
        cons = [i for i in range(start, end) if buf[i].cat == C]
        reph = (len(cons) > 1 and buf[start].cp in RA and start + 1 < end and buf[start + 1].cat == H)
        candidates = cons[1:] if reph else cons
        base = candidates[-1]
        if len(candidates) > 1 and buf[base].cp in RA and buf[base - 1].cat == H:
            base = candidates[-2]
        for i in range(start, end):
            info = buf[i]
            if reph and i < start + 2:
                info.pos, info.mask = POS_REPH, info.mask | plan.masks[b"rphf"]
            elif i < base:
                info.pos, info.mask = POS_PRE_C, info.mask | plan.masks[b"half"]
            elif i == base:
                info.pos = POS_BASE
            elif info.cat == M and INDIC_POSITIONAL.get(info.cp) == PRE_BASE_POSITION:
                info.pos = POS_PRE_M
            elif info.cat == SM:
                info.pos = POS_SMVD
            elif info.cat == M:
                info.pos = POS_MATRA
            else:
                info.pos = POS_POST_C
                info.mask |= plan.masks[b"blwf"] | plan.masks[b"pstf"] | plan.masks[b"abvf"]
        first = start + 2 if reph else start
        moved = [buf[i] for i in range(first, end) if buf[i].pos == POS_PRE_M]
        if moved:
            rest = [buf[i] for i in range(first, end) if buf[i].pos != POS_PRE_M]
            buf[first:end] = moved + rest

    def pause(self, stage: int, buf, plan: Plan, font) -> None:
        if stage != FINAL_STAGE:
            return
        i = 0
        while i < len(buf):
            j = i
            while j < len(buf) and buf[j].syllable == buf[i].syllable:
                j += 1
            if buf[i].syllable:
                self._final(buf, i, j)
            i = j

    @staticmethod
    def _final(buf, start: int, end: int) -> None:
        seg = buf[start:end]
        reph = None
        if seg[0].pos == POS_REPH and (len(seg) < 2 or seg[1].pos != POS_REPH):
            reph = seg.pop(0)
        matras = [g for g in seg if g.pos == POS_PRE_M]
        rest = [g for g in seg if g.pos != POS_PRE_M]
        if matras:
            base = next((k for k, g in enumerate(rest) if g.pos >= POS_BASE), len(rest))
            halant = max((k for k in range(base) if rest[k].cat == H), default=-1)
            rest[halant + 1:halant + 1] = matras
        if reph is not None:
            k = len(rest)
            while k > 0 and rest[k - 1].pos == POS_SMVD:
                k -= 1
            rest.insert(k, reph)
        buf[start:end] = rest
