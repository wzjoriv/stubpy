"""Arabic shaping: joining analysis, positional forms, required ligatures and presentation-form fallback."""
from __future__ import annotations

import unicodedata

from .._ucd import JOINING_TYPES
from ._base import COMMON_STAGES, Plan, Shaper

FORMS = (b"isol", b"fina", b"fin2", b"fin3", b"medi", b"med2", b"init")
ISOL, FINA, MEDI, INIT = b"isol", b"fina", b"medi", b"init"
TRANSPARENT_CATEGORIES = frozenset({"Mn", "Me", "Cf"})
ZWNJ = 0x200C
JOIN_PREVIOUS = frozenset({"R", "D", "C"})
JOIN_NEXT = frozenset({"L", "D", "C"})
PRESENTATION_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
FORM_NAMES = {"<isolated>": ISOL, "<final>": FINA, "<medial>": MEDI, "<initial>": INIT}
_presentation: dict[tuple[int, bytes], int] = {}


def joining_type(cp: int) -> str:
    """The Arabic joining type (``U``, ``R``, ``L``, ``D``, ``C`` or ``T``)."""
    found = JOINING_TYPES.get(cp)
    if found is not None:
        return found
    if cp != ZWNJ and unicodedata.category(chr(cp)) in TRANSPARENT_CATEGORIES:
        return "T"
    return "U"


def joining_forms(cps: list[int]) -> list[bytes | None]:
    """The positional form feature of each code point (``None`` for transparent and non-joining)."""
    types = [joining_type(cp) for cp in cps]
    forms: list[bytes | None] = [None] * len(cps)
    solid = [i for i, t in enumerate(types) if t != "T"]
    for k, i in enumerate(solid):
        t = types[i]
        if t == "U":
            continue
        prev = types[solid[k - 1]] if k > 0 else "U"
        nxt = types[solid[k + 1]] if k + 1 < len(solid) else "U"
        back = t in JOIN_PREVIOUS and prev in JOIN_NEXT
        ahead = t in JOIN_NEXT and nxt in JOIN_PREVIOUS
        if t != "C":
            forms[i] = MEDI if back and ahead else FINA if back else INIT if ahead else ISOL
    return forms


def presentation_form(cp: int, form: bytes) -> int | None:
    """The Unicode presentation-form character for ``cp`` in ``form`` (fonts without GSUB)."""
    if not _presentation:
        for lo, hi in PRESENTATION_RANGES:
            for p in range(lo, hi + 1):
                parts = unicodedata.decomposition(chr(p)).split()
                if len(parts) == 2 and parts[0] in FORM_NAMES:
                    _presentation.setdefault((int(parts[1], 16), FORM_NAMES[parts[0]]), p)
    return _presentation.get((cp, form))


class ArabicShaper(Shaper):
    """Arabic, Syriac and N'Ko."""

    def stages(self, vertical: bool = False) -> list[tuple[bytes, ...]]:
        return [*COMMON_STAGES, *((f,) for f in FORMS), (b"rlig",), (b"calt",), (b"rclt", b"liga", b"clig", b"mset")]

    def setup(self, buf, plan: Plan, font) -> None:
        for tag in FORMS:
            plan.mask(tag, global_=False)
        forms = joining_forms([info.cp for info in buf])
        has_gsub = font.layout is not None and font.layout.gsub is not None
        for info, form in zip(buf, forms):
            if form is None:
                continue
            info.mask |= plan.masks[form]
            if not has_gsub:
                alt = presentation_form(info.cp, form)
                gid = font.glyph_index(chr(alt)) if alt is not None else 0
                if gid:
                    info.gid = gid
