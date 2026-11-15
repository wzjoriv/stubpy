"""Text layout and rendering with real fonts: anchors, spacing, positions, textPath, decorations."""
from __future__ import annotations

import numpy as np
import pytest

import svgraster
from svgraster.dom.document import Document
from svgraster.render.text import decorations, layout_for
from svgraster.render.text._content import collect
from tests.conftest import render_float, svg
from tests.test_fonts import TTF, needs_ttf

FAMILY = "Arial, 'DejaVu Sans', 'Liberation Sans', sans-serif"


def _ink_columns(img: np.ndarray) -> np.ndarray:
    return np.nonzero(img[..., 3].max(axis=0) > 0.3)[0]


def _ink_rows(img: np.ndarray) -> np.ndarray:
    return np.nonzero(img[..., 3].max(axis=1) > 0.3)[0]


def _layout(markup: str):
    doc = Document.parse(markup)
    text = next(n for n in doc.root.iter() if n.tag == "text")
    return layout_for(text, (200.0, 100.0), doc)


def test_whitespace_collapses_and_preserves():
    doc = Document.parse(svg('<text>  a \n  b<tspan>  c</tspan>  </text>'
                             '<text xml:space="preserve"> a\tb </text>'))
    texts = [n for n in doc.root.iter() if n.tag == "text"]
    assert "".join(c.text for c in collect(texts[0], (20, 20))) == "a b c"
    assert "".join(c.text for c in collect(texts[1], (20, 20))) == " a b "


def test_position_lists_apply_per_character():
    doc = Document.parse(svg('<text x="1 2 3" y="9" dx="0 5" rotate="10 20">abcd<tspan x="50">e</tspan></text>'))
    chars = collect(next(n for n in doc.root.iter() if n.tag == "text"), (20, 20))
    assert [c.x for c in chars] == [1, 2, 3, None, 50]
    assert [c.dx for c in chars][:2] == [0, 5]
    assert [c.rotate for c in chars] == [10, 20, 20, 20, 20]


@needs_ttf
class TestLayout:
    def test_anchor_middle_centres_each_chunk(self):
        left = _layout(svg(f'<text x="100" y="50" font-family="{FAMILY}" font-size="20">Hello</text>', 200, 100))
        mid = _layout(svg(f'<text x="100" y="50" text-anchor="middle" font-family="{FAMILY}" '
                          f'font-size="20">Hello</text>', 200, 100))
        width = left.glyphs[-1].x + left.glyphs[-1].advance - left.glyphs[0].x
        assert mid.glyphs[0].x == pytest.approx(100 - width / 2)

    def test_letter_and_word_spacing(self):
        base = _layout(svg(f'<text font-family="{FAMILY}" font-size="20">a b</text>', 200, 100))
        spaced = _layout(svg(f'<text font-family="{FAMILY}" font-size="20" letter-spacing="3" '
                             f'word-spacing="7">a b</text>', 200, 100))
        assert spaced.glyphs[2].x - base.glyphs[2].x == pytest.approx(2 * 3 + 7)

    def test_kerning_tightens_av(self):
        kerned = _layout(svg(f'<text font-family="{FAMILY}" font-size="40">AV</text>', 200, 100))
        plain = _layout(svg(f'<text font-family="{FAMILY}" font-size="40" kerning="0">AV</text>', 200, 100))
        assert kerned.glyphs[1].x < plain.glyphs[1].x

    def test_text_length_stretches(self):
        lay = _layout(svg(f'<text font-family="{FAMILY}" font-size="20" textLength="150">abc</text>', 200, 100))
        last = lay.glyphs[-1]
        assert last.x + last.advance == pytest.approx(150, abs=1e-6)
        squeezed = _layout(svg(f'<text font-family="{FAMILY}" font-size="20" textLength="20" '
                               f'lengthAdjust="spacingAndGlyphs">abc</text>', 200, 100))
        assert squeezed.glyphs[0].hscale < 1

    def test_baseline_shift_super_and_sub(self):
        lay = _layout(svg(f'<text y="50" font-family="{FAMILY}" font-size="30">a<tspan baseline-shift="super">b'
                          f'</tspan><tspan baseline-shift="sub">c</tspan></text>', 200, 100))
        assert lay.glyphs[1].y < lay.glyphs[0].y < lay.glyphs[2].y

    def test_dominant_baseline_middle(self):
        normal = _layout(svg(f'<text y="50" font-family="{FAMILY}">x</text>', 200, 100))
        middle = _layout(svg(f'<text y="50" font-family="{FAMILY}" dominant-baseline="middle">x</text>', 200, 100))
        assert middle.glyphs[0].y > normal.glyphs[0].y

    def test_text_path_follows_curve(self):
        lay = _layout(svg(f'<path id="p" d="M10 80 Q100 0 190 80" fill="none"/><text font-family="{FAMILY}" '
                          f'font-size="12"><textPath href="#p" startOffset="10">curved text here</textPath></text>',
                          200, 100))
        angles = [g.angle for g in lay.glyphs if g.visible]
        assert angles[0] < -10 and angles[-1] > angles[0] and all(g.on_path for g in lay.glyphs)

    def test_decorations(self):
        lay = _layout(svg(f'<text x="10" y="50" font-family="{FAMILY}" font-size="20" '
                          f'text-decoration="underline line-through">Deco</text>', 200, 100))
        kinds = {d.kind: d for d in decorations(lay)}
        assert set(kinds) == {"underline", "line-through"}
        assert kinds["underline"].polygon[:, 1].min() > 50 > kinds["line-through"].polygon[:, 1].max()


@needs_ttf
class TestRendering:
    def test_glyphs_are_filled_outlines(self):
        img = render_float(svg(f'<text x="5" y="40" font-family="{FAMILY}" font-size="40" fill="blue">O</text>',
                               60, 50))
        rows = _ink_rows(img)
        assert 8 < rows.min() and rows.max() <= 41
        centre = img[rows.mean().astype(int), _ink_columns(img).mean().astype(int)]
        assert centre[3] < 0.1
        assert img[..., 2].max() == pytest.approx(1.0) and img[..., 0].max() == 0

    def test_middle_anchor_centres_ink(self):
        img = render_float(svg(f'<text x="50" y="30" text-anchor="middle" font-family="{FAMILY}" '
                               f'font-size="20">HHH</text>', 100, 40))
        cols = _ink_columns(img)
        assert abs((cols.min() + cols.max()) / 2 - 50) < 2

    def test_stroked_text_without_fill(self):
        img = render_float(svg(f'<text x="5" y="40" font-family="{FAMILY}" font-size="40" fill="none" '
                               f'stroke="red" stroke-width="2">O</text>', 60, 50))
        assert img[..., 3].max() > 0.9 and img[..., 0].max() == pytest.approx(1.0)
        rows = _ink_rows(img)
        assert img[int(rows.mean()), _ink_columns(img).mean().astype(int), 3] < 0.1

    def test_rotated_glyphs_change_ink(self):
        plain = render_float(svg(f'<text x="10" y="30" font-family="{FAMILY}" font-size="20">I</text>', 40, 40))
        turned = render_float(svg(f'<text x="10" y="30" rotate="90" font-family="{FAMILY}" font-size="20">I</text>',
                                  40, 40))
        assert len(_ink_rows(turned)) < len(_ink_rows(plain))

    def test_underline_pixels_below_baseline(self):
        plain = render_float(svg(f'<text x="2" y="20" font-family="{FAMILY}" font-size="16">iiii</text>', 60, 30))
        img = render_float(svg(f'<text x="2" y="20" font-family="{FAMILY}" font-size="16" '
                               f'text-decoration="underline">iiii</text>', 60, 30))
        assert plain[20:24, :, 3].max() < 0.05 and img[20:24, 4:12, 3].max() > 0.5

    def test_font_face_rule_with_local_file(self, tmp_path):
        font = tmp_path / "fonts" / "mine.ttf"
        font.parent.mkdir()
        font.write_bytes(TTF.read_bytes())
        doc = tmp_path / "doc.svg"
        doc.write_text(svg('<style>@font-face { font-family: Mine; src: url("fonts/mine.ttf") format("truetype"); }'
                           '</style><text x="2" y="30" font-family="Mine" font-size="30">W</text>', 50, 40))
        layout = layout_for(next(n for n in Document.parse(doc).root.iter() if n.tag == "text"), (50, 40),
                            Document.parse(doc))
        assert layout.glyphs[0].font.source == str(font)
        assert svgraster.render(doc)[..., 3].max() == 255

    def test_bold_and_italic_change_rendering(self):
        regular = render_float(svg(f'<text x="2" y="30" font-family="{FAMILY}" font-size="24">Ab</text>', 60, 40))
        bold = render_float(svg(f'<text x="2" y="30" font-family="{FAMILY}" font-size="24" '
                                f'font-weight="bold">Ab</text>', 60, 40))
        assert bold[..., 3].sum() > regular[..., 3].sum() * 1.15


def test_unknown_family_still_renders():
    img = render_float(svg('<text x="2" y="15" font-family="NoSuchFace" font-size="12">AB</text>', 40, 20))
    assert img[..., 3].max() > 0.9
