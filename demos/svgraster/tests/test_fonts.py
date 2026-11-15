"""Font parsing (glyf, CFF, cmap, kerning), discovery, matching and SVG fonts."""
from __future__ import annotations

import numpy as np
import pytest

from svgraster import _backend
from svgraster.dom.document import Document
from svgraster.dom.transform import Matrix
from svgraster.fonts import Font, FontDatabase, FontFormatError, SvgFont, font_faces, parse_family_list, weight_value
from svgraster.fonts._glyf import py_simple_glyph
from svgraster.fonts._scan import describe, system_font_dirs
from svgraster.fonts.database import _weight_rank
from svgraster.fonts.strokefont import StrokeFont
from tests.conftest import svg

FONT_DIRS = [d for d in system_font_dirs()]


def _find(*names: str):
    for folder in FONT_DIRS:
        for name in names:
            for path in folder.rglob(name):
                return path
    return None


TTF = _find("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")
OTF = _find("*.otf")
TTC = _find("*.ttc")
needs_ttf = pytest.mark.skipif(TTF is None, reason="no Arial, DejaVu Sans or Liberation Sans installed")


@pytest.fixture(scope="module")
def face() -> Font:
    if TTF is None:
        pytest.skip("no TrueType test font")
    return Font.from_file(TTF)


@needs_ttf
class TestTrueType:
    def test_tables(self, face):
        assert face.outline_format == "glyf"
        assert face.units_per_em in (1000, 2048)
        assert face.num_glyphs > 200 and face.weight == 400 and not face.italic
        assert face.family.lower() in ("arial", "dejavu sans", "liberation sans")
        m = face.metrics
        assert m.ascent > 0 > m.descent and m.underline_position < 0 and m.underline_thickness > 0

    def test_cmap_and_advances(self, face):
        a, i = face.glyph_index("A"), face.glyph_index("i")
        assert a and i and a != i
        assert face.glyph_index("\U0010fffd") == 0
        assert face.advance(face.glyph_index("W")) > face.advance(i) > 0
        assert face.text_width("AAAA", 10) == pytest.approx(4 * face.text_width("A", 10))

    def test_kerning_pairs(self, face):
        av = face.kern(face.glyph_index("A"), face.glyph_index("V"))
        assert av < 0
        assert face.kern(face.glyph_index("H"), face.glyph_index("H")) == 0

    def test_outline_contours(self, face):
        o = face.outline(face.glyph_index("o"))
        assert sum(seg[0] == "M" for seg in o.segments) == 2
        assert any(seg[0] == "Q" for seg in o.segments)
        assert all(seg[0] in "MLQZ" for seg in o.segments)

    def test_composite_glyph(self, face):
        plain = face.outline(face.glyph_index("e"))
        accented = face.outline(face.glyph_index("é"))
        assert sum(s[0] == "M" for s in accented.segments) > sum(s[0] == "M" for s in plain.segments)

    def test_glyph_polygons_are_scaled(self, face):
        s = 50.0 / face.units_per_em
        polys = face.glyph_polygons(face.glyph_index("H"), Matrix.translate(10, 60) @ Matrix.scale(s, -s), 0.1)
        pts = np.concatenate(polys)
        assert 10 <= pts[:, 0].min() < pts[:, 0].max() < 50
        assert 20 < pts[:, 1].min() and pts[:, 1].max() == pytest.approx(60, abs=1)

    def test_native_glyph_decoder_matches_python(self, face):
        native = _backend.module("glyf")
        if native is None:
            pytest.skip("svgraster._glyf is not built")
        out = face._outlines
        for ch in "AgQ&8":
            gid = face.glyph_index(ch)
            pos = out.base + int(out.offsets[gid])
            ends, packed = native.simple_glyph(out.data, pos)
            py_ends, py_pts = py_simple_glyph(out.data, pos)
            assert list(ends) == py_ends
            np.testing.assert_array_equal(np.frombuffer(packed, np.int32).reshape(-1, 3), py_pts)
            assert native.glyph_header(out.data, pos)[0] == len(py_ends)


def test_describe_reads_names_without_full_parse():
    if TTF is None:
        pytest.skip("no TrueType test font")
    (info,) = describe(TTF)
    assert info.family and info.weight == 400 and info.family.lower() in info.aliases


@pytest.mark.skipif(OTF is None, reason="no OpenType CFF font installed")
def test_cff_outlines():
    font = Font.from_file(OTF)
    gid = next(font.glyph_index(c) for c in "AaHx0" if font.has_glyph(c))
    path = font.outline(gid)
    assert font.outline_format in ("cff", "glyf")
    if font.outline_format == "cff":
        assert path.segments and path.segments[0][0] == "M"
        assert any(s[0] == "C" for s in path.segments) or any(s[0] == "L" for s in path.segments)


@pytest.mark.skipif(TTC is None, reason="no font collection installed")
def test_collections_expose_every_face():
    faces = font_faces(TTC)
    assert len(faces) >= 2 and len({f.index for f in faces}) == len(faces)


def test_rejects_non_fonts(tmp_path):
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"not a font at all")
    with pytest.raises(FontFormatError):
        Font.from_file(bad)
    assert describe(bad) == []


def test_family_lists_and_weights():
    assert parse_family_list("'Times New Roman', Georgia ,serif") == ["Times New Roman", "Georgia", "serif"]
    assert weight_value("bold") == 700 and weight_value("normal") == 400 and weight_value("600") == 600
    assert weight_value("bolder", 400) == 700
    ranked = sorted([300, 400, 500, 700], key=lambda w: _weight_rank(400, w))
    assert ranked[0] == 400 and ranked[1] == 500
    assert sorted([300, 500, 900], key=lambda w: _weight_rank(700, w))[0] == 900


@needs_ttf
def test_database_matching_user_folder(tmp_path):
    copy = tmp_path / "custom.ttf"
    copy.write_bytes(TTF.read_bytes())
    db = FontDatabase([tmp_path])
    family = db.faces[0].family
    found = db.match(f"NoSuchFamily, '{family}'", "bold", italic=True)
    assert found and found[0].font.family == family
    assert found[0].synthetic_bold and found[0].synthetic_oblique
    assert db.match_family("NoSuchFamily") is None
    with pytest.raises(FileNotFoundError):
        db.add_path(tmp_path / "missing")


def test_generic_family_falls_back():
    db = FontDatabase([], parent=None)
    font = StrokeFont()
    db.add_font(font, "Only")
    assert db.match_family("sans-serif") is None
    assert db.match("Only")[0].font is font


SVG_FONT = svg(
    '<defs><font id="f" horiz-adv-x="500"><font-face font-family="Boxes" units-per-em="1000" ascent="800" '
    'descent="200"/><missing-glyph d="M0 0 H100 V100 H0z"/>'
    '<glyph unicode="a" d="M0 0 H400 V700 H0z"/><glyph unicode="ab" horiz-adv-x="900" d="M0 0 H800 V300 H0z"/>'
    '<glyph unicode="b" glyph-name="bee" d="M0 0 H200 V700 H0z"/><hkern u1="a" g2="bee" k="250"/></font></defs>'
    '<text x="1" y="15" font-family="Boxes" font-size="10">a</text>', 30, 20)


def test_svg_font_parsing():
    doc = Document.parse(SVG_FONT)
    font = SvgFont(doc.ids["f"])
    assert font.family == "Boxes" and font.units_per_em == 1000
    assert font.map_text("abba") == [(font.glyph_index("ab"), 2), (font.glyph_index("b"), 1),
                                     (font.glyph_index("a"), 1)]
    assert font.kern(font.glyph_index("a"), font.glyph_index("b")) == -250
    assert font.advance(font.glyph_index("ab")) == 900 and font.map_text("z") == [(0, 1)]


def test_svg_font_renders_glyph_boxes():
    import svgraster

    img = svgraster.render(SVG_FONT, dtype="float32", antialias=8)
    alpha = img[..., 3]
    assert alpha[12, 3] > 0.9 and alpha[12, 6] < 0.05 and alpha[5, 3] < 0.05


def test_stroke_font_is_last_resort():
    font = StrokeFont(700)
    gid = font.glyph_index("Q")
    assert font.has_glyph("Q") and font.has_glyph("q") and not font.has_glyph("漢")
    polys = font.glyph_polygons(gid, Matrix.scale(1.0, -1.0), 0.1)
    assert polys and font.kern(gid, gid) == 0 and font.advance(gid) > 0
