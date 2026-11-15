"""The Unicode Bidirectional Algorithm: mixed strings, SVG properties and the official conformance file."""
from __future__ import annotations

from pathlib import Path

import pytest

from svgraster._backend import pure_python
from svgraster.dom.document import Document
from svgraster.render.text import layout_for
from svgraster.shaping.bidi import LTR, RTL, paragraph
from tests.conftest import native_module, svg

TEST_FILE = Path(__file__).resolve().parents[1] / "conformance" / "suite" / "unicode" / "BidiCharacterTest.txt"
AUTO = 2
MIN_PASS_RATE = 1.0


def _visual(text: str, direction=None) -> str:
    para = paragraph(text, direction)
    return "".join(para.mirror(i) for i in para.visual_order())


def test_hebrew_reverses_inside_ltr():
    assert _visual("ab אבג cd", LTR) == "ab גבא cd"


def test_numbers_keep_their_order_in_rtl():
    assert _visual("א 123 ב", RTL) == "ב 123 א"


def test_auto_direction_from_first_strong():
    assert paragraph("אbc").level == RTL
    assert paragraph("abcא").level == LTR


def test_brackets_are_mirrored():
    assert _visual("א(ב)", RTL) == "(ב)א"


def test_explicit_override_and_isolate():
    assert _visual("‮abc‬", LTR).replace("‮", "").replace("‬", "") == "cba"
    para = paragraph("⁧abc⁩ d", LTR)
    assert para.levels[1:4] == [2, 2, 2]


def test_native_matches_python():
    native_module("_bidi")
    text = "a1 (אב 2.5%) العربية 123 [x]"
    with pure_python():
        expected = paragraph(text).levels
    assert paragraph(text).levels == expected


def _cases():
    for line in TEST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            yield line.split(";")


def test_bidi_character_test_file():
    if not TEST_FILE.exists():
        pytest.skip("BidiCharacterTest.txt missing; run: python scripts/dev.py demos svgraster gen-unicode")
    passed = total = 0
    for fields in _cases():
        text = "".join(chr(int(c, 16)) for c in fields[0].split())
        direction = int(fields[1])
        para = paragraph(text, None if direction == AUTO else direction)
        removed = para.removed
        levels = para.line_levels()
        got = ["x" if removed[i] else str(levels[i]) for i in range(len(text))]
        order = [str(i) for i in para.visual_order() if not removed[i]]
        total += 1
        passed += got == fields[3].split() and order == fields[4].split() and para.level == int(fields[2])
    assert passed / total >= MIN_PASS_RATE, f"{passed}/{total}"


def _chars_in_visual_order(markup: str) -> str:
    doc = Document.parse(markup)
    text = next(n for n in doc.root.iter() if n.tag == "text")
    layout = layout_for(text, (200.0, 100.0), doc)
    return "".join(g.char.text for g in sorted(layout.glyphs, key=lambda g: g.x))


def test_layout_orders_glyphs_visually():
    order = _chars_in_visual_order(svg('<text x="10" y="20" font-family="Arial">ab אב</text>', 200, 100))
    assert order == "ab בא"


def test_unicode_bidi_override_property():
    order = _chars_in_visual_order(svg('<text x="10" y="20" font-family="Arial">a<tspan direction="rtl" '
                                       'unicode-bidi="bidi-override">bcd</tspan></text>', 200, 100))
    assert order == "adcb"


def _bet_x(dx: str) -> float:
    doc = Document.parse(svg(f'<text x="100" y="20" font-family="Arial" direction="rtl" dx="{dx}">'
                             'אב</text>', 200, 100))
    text = next(n for n in doc.root.iter() if n.tag == "text")
    return next(g.x for g in layout_for(text, (200.0, 100.0), doc).glyphs if g.char.text == "ב")


def test_dx_applies_to_logical_characters():
    assert _bet_x("0 30") != _bet_x("0 0")
