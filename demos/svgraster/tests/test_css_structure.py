"""CSS selectors and at-rules, system colors, namespaces, switch conditions and external references."""
from __future__ import annotations

import numpy as np
import pytest

import svgraster
from svgraster.dom import parse_color
from svgraster.dom.css import Stylesheet, parse_selector
from svgraster.dom.document import Document
from svgraster.dom.style import expand_font
from svgraster.render._switch import passes_conditions
from tests.conftest import SVG_NS, render_float, svg


def _fill(markup: str, ident: str) -> str:
    return Document.parse(markup).ids[ident].style["fill"]


class TestSelectors:
    @pytest.mark.parametrize("sel,ident", [
        ('[data-k]', "a"), ('[data-k="v w"]', "a"), ('[data-k~="w"]', "a"), ('[lang|="en"]', "b"),
        ('[data-k^="v"]', "a"), ('[data-k$=" w"]', "a"), ('[data-k*=" "]', "a"),
        ("rect:first-child", "a"), ("rect:last-child", "c"), ("g > rect + rect", "b"), ("#a ~ rect", "c"),
        (":lang(en)", "b"), ("rect:nth-child(2)", "b"), ("rect:nth-child(odd)", "c"),
    ])
    def test_matching(self, sel, ident):
        markup = svg(f'<style>rect {{ fill: blue }} {sel} {{ fill: red }}</style><g>'
                     '<rect id="a" data-k="v w"/><rect id="b" lang="en-US"/><rect id="c"/></g>')
        assert _fill(markup, ident) == "red"

    def test_never_matching_pseudo_classes(self):
        markup = svg('<style>rect:hover { fill: red } a:visited rect { fill: red }</style><rect id="a"/>')
        assert _fill(markup, "a") == "black"

    def test_specificity_is_lexicographic(self):
        sel = parse_selector("g > rect.a#b")
        assert sel.specificity == (1, 1, 2)
        markup = svg('<style>#x { fill: green } .a.b.c.d.e.f.g.h.i.j.k { fill: red }</style>'
                     '<rect id="x" class="a b c d e f g h i j k"/>')
        assert _fill(markup, "x") == "green"

    def test_unsupported_selectors_are_skipped(self):
        assert parse_selector("p::before") is None
        assert parse_selector("a:not(.b)") is None
        sheet = Stylesheet()
        sheet.extend("p::after, rect { fill: red }")
        assert len(sheet.rules) == 1


class TestAtRules:
    def test_media_and_font_face(self):
        sheet = Stylesheet()
        sheet.extend("@media print { rect { fill: red } } @media screen, print { rect { fill: blue } }"
                     "@font-face { font-family: 'X'; src: url(x.ttf) } @charset 'utf-8';")
        assert len(sheet.rules) == 1 and sheet.rules[0].declarations[0].value == "blue"
        assert sheet.font_faces == [{"font-family": "'X'", "src": "url(x.ttf)"}]

    def test_import_and_xml_stylesheet(self, tmp_path):
        (tmp_path / "a.css").write_text("@import 'b.css'; circle { fill: red }")
        (tmp_path / "b.css").write_text("rect { fill: lime }")
        (tmp_path / "pi.css").write_text("ellipse { fill: navy }")
        doc = tmp_path / "doc.svg"
        doc.write_text('<?xml-stylesheet type="text/css" href="pi.css"?>' + svg(
            '<style>@import url("a.css");</style><rect id="r"/><circle id="c"/><ellipse id="e"/>'))
        parsed = Document.parse(doc)
        assert [parsed.ids[k].style["fill"] for k in "rce"] == ["lime", "red", "navy"]

    def test_font_shorthand(self):
        assert expand_font("italic bold 12px/30px Georgia, serif") == {
            "font-style": "italic", "font-variant": "normal", "font-weight": "bold", "font-size": "12px",
            "font-family": "Georgia, serif"}
        doc = Document.parse(svg('<text id="t" style="font: 20px Courier">x</text>'))
        assert doc.ids["t"].font_size == 20 and doc.ids["t"].style["font-family"] == "Courier"


def test_system_colors():
    assert parse_color("ButtonFace") is not None and parse_color("windowtext").r == 0
    img = render_float(svg('<rect width="20" height="20" fill="Highlight"/>'))
    assert img[5, 5, 3] == 1.0


class TestStructure:
    def test_foreign_namespace_elements_are_ignored(self):
        markup = (f'<svg {SVG_NS} xmlns:o="http://example.org/other" width="20" height="20">'
                  '<o:rect width="20" height="20" fill="red"/><rect o:fill="red" width="5" height="5"/></svg>')
        img = render_float(markup)
        assert img[10, 10, 3] == 0 and img[2, 2, 0] == 0 and img[2, 2, 3] == 1

    def test_switch_conditions(self, monkeypatch):
        monkeypatch.setenv("SVGRASTER_LANG", "fr-CA")
        doc = Document.parse(svg('<switch><rect id="a" systemLanguage="de"/><rect id="b" systemLanguage="fr"/>'
                                 '<rect id="c"/></switch><rect id="d" requiredExtensions="http://x"/>'
                                 '<rect id="e" requiredFeatures="http://www.w3.org/TR/SVG11/feature#Shape"/>'))
        assert [passes_conditions(doc.ids[k]) for k in "abcde"] == [False, True, True, False, True]
        img = render_float(svg('<switch><rect width="20" height="20" fill="red" systemLanguage="de"/>'
                               '<rect width="20" height="20" fill="lime" systemLanguage="fr"/></switch>'))
        assert img[5, 5, 1] == 1.0 and img[5, 5, 0] == 0

    def test_external_use_and_its_own_gradients(self, tmp_path):
        (tmp_path / "lib.svg").write_text(svg(
            '<defs><linearGradient id="g"><stop offset="0" stop-color="lime"/><stop offset="1" stop-color="lime"/>'
            '</linearGradient></defs><rect id="r" width="10" height="10" fill="url(#g)"/>'))
        doc = tmp_path / "main.svg"
        doc.write_text(svg('<defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs>'
                           '<use href="lib.svg#r" x="5" y="5"/>'))
        img = svgraster.render(doc)
        assert img[10, 10].tolist() == [0, 255, 0, 255] and img[2, 2, 3] == 0

    def test_use_of_svg_keeps_its_position(self):
        img = render_float(svg('<defs><svg id="s" x="10" y="0" width="10" height="10"><rect width="100%" '
                               'height="100%" fill="blue"/></svg></defs><use href="#s"/>'))
        assert img[5, 15, 2] == 1.0 and img[5, 5, 3] == 0

    def test_duck_typed_and_gzip_sources(self, tmp_path):
        import gzip

        markup = svg('<rect width="20" height="20" fill="lime"/>')

        class Drawing:
            def __svg__(self):
                return markup

        class Legacy:
            def to_string(self):
                return markup

        for source in (Drawing(), Legacy(), gzip.compress(markup.encode())):
            assert svgraster.render(source)[5, 5].tolist() == [0, 255, 0, 255]
        with pytest.raises(TypeError, match="__svg__"):
            svgraster.render(object())
        path = tmp_path / "x.svgz"
        path.write_bytes(gzip.compress(markup.encode()))
        assert svgraster.render(path)[5, 5, 1] == 255

    def test_error_messages_name_the_file(self, tmp_path):
        bad = tmp_path / "bad.svg"
        bad.write_text("<svg")
        with pytest.raises(ValueError, match="bad.svg"):
            svgraster.render(bad)
        with pytest.raises(FileNotFoundError, match="missing.svg"):
            svgraster.render(tmp_path / "missing.svg")
        with pytest.raises(TypeError, match="unexpected keyword"):
            svgraster.render(svg(""), antialiasing=3)

    def test_forced_size_letterboxes_view_box(self):
        img = render_float(svg('<rect width="10" height="10" fill="red"/>', 10, 10, 'viewBox="0 0 10 10"'),
                           width=40, height=20)
        assert img.shape[:2] == (20, 40) and img[10, 2, 3] == 0 and img[10, 20, 3] == 1.0
        assert np.all(img[..., 3][:, 10:30] == 1.0)
