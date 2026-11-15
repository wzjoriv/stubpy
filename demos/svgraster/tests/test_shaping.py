"""Complex shaping with system fonts: Arabic, Hebrew, Devanagari, Thai and Latin ligatures."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from svgraster.fonts import Font, font_faces
from svgraster.shaping._itemize import scripts
from svgraster.shaping._shape import shape
from svgraster.shaping.shapers._arabic import joining_forms
from svgraster.shaping.shapers._indic import C, H, M, category, syllables
from tests.conftest import render_float, svg

FONTS = Path("C:/Windows/Fonts") if sys.platform == "win32" else Path("/usr/share/fonts")
SALAM = "\u0633\u0644\u0627\u0645"
SHALOM = "\u05e9\u05b8\u05c1\u05dc\u05d5\u05b9\u05dd"
KSSI = "\u0915\u094d\u0937\u093f"
RKI = "\u0930\u094d\u0915\u093f"
KO_AM = "\u0e01\u0e33"


def _font(name: str, index: int = 0) -> Font:
    path = FONTS / name
    if not path.exists():
        pytest.skip(f"{name} not installed")
    return font_faces(path)[index] if path.suffix.lower() == ".ttc" else Font.from_file(path)


def _gids(font, text, script, rtl=False):
    return [g.gid for g in shape(font, text, script, rtl)]


def _cmap(font, text):
    return [font.glyph_index(ch) for ch in text]


def test_arabic_joining_forms():
    assert joining_forms([ord(c) for c in SALAM]) == [b"init", b"fina", None, b"isol"] or \
        joining_forms([ord(c) for c in SALAM])[:2] == [b"init", b"medi"]
    assert joining_forms([0x0628, 0x0628, 0x0628]) == [b"init", b"medi", b"fina"]
    assert joining_forms([0x0628, 0x064E, 0x0628]) == [b"init", None, b"fina"]
    assert joining_forms([0x0627, 0x0628]) == [b"isol", b"isol"]


def test_arabic_salam_forms_and_lam_alef():
    arial = _font("arial.ttf")
    expected = _cmap(arial, "\ufee1\ufefc\ufeb3")
    if 0 in expected:
        pytest.skip("font lacks presentation-form cmap entries")
    assert _gids(arial, SALAM, "Arabic", rtl=True) == expected


def test_lam_alef_required_ligature():
    arial = _font("arial.ttf")
    assert _gids(arial, "\u0644\u0627", "Arabic", rtl=True) == _cmap(arial, "\ufefb")


def test_arabic_rtl_glyphs_run_right_to_left():
    arial = _font("arial.ttf")
    glyphs = shape(arial, SALAM, "Arabic", rtl=True)
    assert [g.cluster for g in glyphs] == sorted((g.cluster for g in glyphs), reverse=True)
    xs = [g.x for g in glyphs]
    assert xs == sorted(xs)


def test_hebrew_marks_attach_to_their_base():
    times = _font("times.ttf")
    glyphs = shape(times, SHALOM, "Hebrew", rtl=True)
    marks = [g for g in glyphs if g.is_mark]
    assert marks and all(g.advance == 0 for g in marks)
    bases = [g for g in glyphs if not g.is_mark]
    assert len(bases) == 4
    total = sum(g.advance for g in glyphs)
    assert all(-1 <= g.x <= total for g in marks)


def test_devanagari_syllables():
    cats = [category(ord(c)) for c in KSSI]
    assert cats == [C, H, C, M]
    assert syllables(cats) == [(0, 4)]


def test_devanagari_kssi_reorders_pre_base_matra():
    nirmala = _font("Nirmala.ttc")
    gids = _gids(nirmala, KSSI, "Devanagari")
    assert len(gids) == 2
    assert gids[0] == nirmala.glyph_index("\u093f")
    assert gids[1] not in _cmap(nirmala, KSSI)


def test_devanagari_reph_moves_after_base():
    nirmala = _font("Nirmala.ttc")
    gids = _gids(nirmala, RKI, "Devanagari")
    assert gids[:2] == _cmap(nirmala, "\u093f\u0915")
    assert len(gids) == 3 and gids[2] not in _cmap(nirmala, RKI)


def test_thai_sara_am_decomposes():
    tahoma = _font("tahoma.ttf")
    assert _gids(tahoma, KO_AM, "Thai") == _cmap(tahoma, "\u0e01\u0e4d\u0e32")


def test_latin_fi_ligature():
    calibri = _font("calibri.ttf")
    gids = _gids(calibri, "office", "Latin")
    assert len(gids) < 6
    assert gids[0] == calibri.glyph_index("o") and gids[-1] == calibri.glyph_index("e")


def test_latin_kerning_through_gpos():
    arial = _font("arial.ttf")
    av = shape(arial, "AV", "Latin")
    assert av[0].advance < arial.advance(arial.glyph_index("A"))
    plain = shape(arial, "AV", "Latin", kerning=False)
    assert plain[0].advance == arial.advance(arial.glyph_index("A"))


def test_script_itemization_resolves_common():
    assert scripts("ab 12 \u05d0\u05d1") == ["Latin"] * 6 + ["Hebrew"] * 2


def _ink_columns(img: np.ndarray) -> np.ndarray:
    return np.nonzero(img[..., 3].max(axis=0) > 0.3)[0]


def test_rtl_text_starts_at_the_right():
    _font("arial.ttf")
    markup = svg(f'<text x="100" y="40" font-family="Arial" font-size="24" direction="rtl">{SALAM}</text>', 200, 60)
    cols = _ink_columns(render_float(markup))
    assert cols.size and cols.max() <= 101 and cols.min() < 80


def test_rtl_anchor_end_is_the_left_edge():
    _font("arial.ttf")
    markup = svg('<text x="100" y="40" font-family="Arial" font-size="24" direction="rtl" text-anchor="end">'
                 f'{SALAM}</text>', 200, 60)
    cols = _ink_columns(render_float(markup))
    assert cols.size and cols.min() >= 99 and cols.max() > 120


def test_mixed_text_renders_hebrew_right_of_latin_in_ltr():
    _font("arial.ttf")
    latin = render_float(svg('<text x="10" y="40" font-family="Arial" font-size="24">abc</text>', 200, 60))
    mixed = render_float(svg('<text x="10" y="40" font-family="Arial" font-size="24">abc '
                             '\u05d0\u05d1\u05d2</text>', 200, 60))
    assert _ink_columns(mixed).max() > _ink_columns(latin).max() + 20


def test_arabic_renders_connected_ink():
    _font("arial.ttf")
    img = render_float(svg(f'<text x="10" y="40" font-family="Arial" font-size="32">{SALAM}</text>', 120, 60))
    cols = _ink_columns(img)
    assert cols.size > 20
    gaps = np.diff(cols)
    assert gaps.max() <= 12


def test_vertical_text_stacks_downwards():
    _font("arial.ttf")
    img = render_float(svg('<text x="30" y="10" font-family="Arial" font-size="16" writing-mode="tb" '
                           'glyph-orientation-vertical="0">ABC</text>', 60, 80))
    rows = np.nonzero(img[..., 3].max(axis=1) > 0.3)[0]
    cols = _ink_columns(img)
    assert rows.max() - rows.min() > 35
    assert cols.max() - cols.min() < 16


def test_sideways_vertical_text_is_rotated():
    _font("arial.ttf")
    img = render_float(svg('<text x="30" y="5" font-family="Arial" font-size="16" writing-mode="tb">'
                           'mmmm</text>', 60, 100))
    rows = np.nonzero(img[..., 3].max(axis=1) > 0.3)[0]
    cols = _ink_columns(img)
    assert rows.max() - rows.min() > 2 * (cols.max() - cols.min())
