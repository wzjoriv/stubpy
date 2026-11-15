from __future__ import annotations

import pytest

import svgwriter as svg
from svgwriter.attributes import Length, Style
from svgwriter.color import Color, PaintKeyword, PaintRef
from svgwriter.elements import Category, ContentModel, Element, UnknownElement
from svgwriter.path import BBox, PathData
from svgwriter.transform import Transform

from .conftest import SVG_NS, make, roundtrip, wellformed


def test_every_svg11_element_is_registered() -> None:
    assert len(svg.Element.registered()) == 80


def test_every_element_serializes(any_tag: str) -> None:
    element = make(any_tag)
    assert element.tag == any_tag
    node = wellformed(element.to_string())
    assert node.tag in (any_tag, SVG_NS + any_tag)


def test_every_element_round_trips(any_tag: str) -> None:
    element = make(any_tag)
    first, second = roundtrip(element)
    assert first == second
    assert type(svg.parse(first)) is type(element)


def test_categories() -> None:
    shapes = set(svg.Element.registered(Category.SHAPE))
    assert shapes == {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path"}
    assert len(svg.Element.registered(Category.FILTER_PRIMITIVE)) == 16
    assert set(svg.Element.registered(Category.LIGHT_SOURCE)) == {"feDistantLight", "fePointLight", "feSpotLight"}
    assert Category.GROUPING is Category.CONTAINER


class TestBasicShapes:
    def test_rect_attributes(self) -> None:
        r = svg.Rect(1, 2, 30, 40, rx=5, fill="red", stroke_width=2)
        assert str(r) == '<rect fill="red" stroke-width="2" x="1" y="2" width="30" height="40" rx="5"/>'
        assert r.bbox == BBox(1, 2, 30, 40)

    def test_rect_factories(self) -> None:
        sq = svg.Rect.square(10, fill="blue")
        assert (sq.get("width"), sq.get("height"), sq.get("fill")) == (10, 10, "blue")
        assert isinstance(sq, svg.Rect)
        assert svg.Rect.from_bbox(BBox(1, 2, 3, 4)).bbox == BBox(1, 2, 3, 4)

    def test_circle(self) -> None:
        c = svg.Circle(10, 10, 5)
        assert c.bbox == BBox(5, 5, 10, 10)
        assert c.area == pytest.approx(78.5398, rel=1e-4)
        assert svg.Circle.from_bbox(BBox(0, 0, 10, 20)).get("r") == 5

    def test_ellipse_line(self) -> None:
        assert svg.Ellipse(10, 10, 5, 2).bbox == BBox(5, 8, 10, 4)
        line = svg.Line(0, 0, 3, 4)
        assert line.length == 5
        assert line.bbox == BBox(0, 0, 3, 4)

    def test_lengths_with_units(self) -> None:
        r = svg.Rect(svg.mm(10), 0, "1in", svg.percent(50))
        assert 'x="10mm"' in str(r) and 'width="1in"' in str(r) and 'height="50%"' in str(r)
        assert r.width == Length(1, svg.Unit.IN)

    def test_polyline_polygon(self) -> None:
        pl = svg.Polyline([(0, 0), (10, 0), (10, 10)])
        assert str(pl) == '<polyline points="0,0 10,0 10,10"/>'
        pg = svg.Polygon("0,0 4,0 4,3")
        assert pg.area == 6
        assert pg.bbox == BBox(0, 0, 4, 3)
        hexagon = svg.Polygon.regular(0, 0, 10, 6)
        assert len(hexagon.points) == 6
        with pytest.raises(ValueError):
            svg.Polyline("1 2 3")

    def test_path(self) -> None:
        p = svg.Path("M0 0 L10 10", path_length=100)
        assert isinstance(p.d, PathData)
        assert p.bbox == BBox(0, 0, 10, 10)
        assert str(p) == '<path d="M0 0 L10 10" pathLength="100"/>'
        closed = svg.Path.from_points([(0, 0), (1, 0), (1, 1)], closed=True)
        assert str(closed.d) == "M0 0 L1 0 L1 1 Z"
        assert svg.Path.build(svg.PathBuilder().move_to(1, 1)).d == PathData("M1 1")

    def test_descriptor_reads_parsed_strings(self) -> None:
        rect = svg.parse('<svg xmlns="http://www.w3.org/2000/svg"><rect x="2mm" width="5" fill="url(#g) red"/></svg>').find(svg.Rect)
        assert rect is not None
        assert rect.x == Length(2, svg.Unit.MM)
        assert rect.width == Length(5)
        assert rect.fill == PaintRef(svg.FuncIRI("#g"), Color(255, 0, 0))
        assert rect.y is None
        del rect.x
        assert rect.x is None


class TestKeywordForwarding:
    def test_deep_chain_reaches_every_group(self) -> None:
        rect = svg.Rect(
            id="r",
            xml_lang="en",
            required_features="http://www.w3.org/TR/SVG11/feature#Shape",
            system_language=["en", "fr"],
            class_=["a", "b"],
            style={"cursor": "pointer"},
            fill="red",
            transform="rotate(5)",
            external_resources_required=False,
            onclick="go()",
        )
        attrs = rect.attributes
        assert next(iter(attrs)) == "id"
        assert attrs["xml:lang"] == "en"
        assert attrs["systemLanguage"] == "en,fr"
        assert attrs["class"] == "a b"
        assert str(attrs["style"]) == "cursor:pointer"
        assert attrs["externalResourcesRequired"] is False
        assert attrs["onclick"] == "go()"
        assert rect.transform == Transform().rotate(5)

    def test_unknown_presentation_attributes_pass_through(self) -> None:
        g = svg.Group(shape_rendering="crispEdges", marker_end="url(#m)", attrs={"data:x": "1"})
        assert g.get("shape-rendering") == "crispEdges"
        assert g.get("marker-end") == "url(#m)"
        assert g.get("data:x") == "1"

    def test_kwargs_pop_before_forwarding(self) -> None:
        t = svg.Text("x", decoration=svg.TextDecoration.LINE_THROUGH | svg.TextDecoration.BLINK)
        assert t.to_string(pretty=False, xml_declaration=False) == '<text text-decoration="line-through blink">x</text>'
        assert svg.TextDecoration.NONE.svg_value() == "none"

    def test_mro_has_every_group(self) -> None:
        names = [c.__name__ for c in svg.Rect.__mro__]
        for group in ("Transformable", "PresentationAttributes", "StyleAttributes", "ConditionalAttributes", "CoreAttributes", "Element"):
            assert group in names


class TestElementApi:
    def test_ids_and_references(self) -> None:
        grad = svg.LinearGradient()
        rect = svg.Rect(fill=grad)
        assert grad.id is not None
        assert rect.get("fill") == svg.FuncIRI("#" + grad.id)
        use = svg.Use.of(rect)
        assert use.get("xlink:href") == svg.IRI("#" + str(rect.ensure_id()))
        assert use.target == rect.id
        with pytest.raises(ValueError):
            rect.id = "1bad id"

    def test_id_is_first_attribute(self) -> None:
        r = svg.Rect(1, 2, 3, 4)
        r.id = "late"
        assert list(r.attributes)[0] == "id"
        r.id = None
        assert "id" not in r.attributes

    def test_set_get_update(self) -> None:
        r = svg.Rect()
        assert r.set("stroke_linecap", "round") is r
        assert r.get("stroke-linecap") == "round"
        assert r.get("missing", 42) == 42
        r.update({"opacity": 0.5}, fill=None)
        assert r.has("opacity") and not r.has("fill")
        r.discard("opacity")
        assert not r.has("opacity")

    def test_presentation_descriptor(self) -> None:
        r = svg.Rect(fill="none", opacity="0.5")
        r.attributes["fill"] = "none"
        assert r.fill is PaintKeyword.NONE
        assert r.opacity == 0.5

    def test_style_property_and_css_moves(self) -> None:
        r = svg.Rect(fill="red", stroke="blue", style="mix-blend-mode:multiply")
        r.to_css()
        assert str(r.attributes["style"]) == "mix-blend-mode:multiply;fill:red;stroke:blue"
        assert "fill" not in r.attributes
        r.from_css()
        assert r.attributes["fill"] == "red"
        assert dict(r.style) == {"mix-blend-mode": "multiply"}
        assert isinstance(r.style, Style)
        r.style = None
        assert "style" not in r.attributes

    def test_classes(self) -> None:
        g = svg.Group(class_="a")
        g.add_class("b", "a")
        assert g.classes == ["a", "b"]

    def test_children(self) -> None:
        g = svg.Group()
        a, b = g.add(svg.Rect()), g.add(svg.Circle())
        assert list(g) == [a, b]
        assert g[1] is b and g[:1] == [a]
        other = svg.Group()
        other.append(a)
        assert a.parent is other and len(g) == 1
        g.insert(0, a)
        assert g[0] is a
        g.remove(a)
        assert a.parent is None
        g.clear()
        assert len(g) == 0

    def test_content_model_enforced(self) -> None:
        with pytest.raises(TypeError):
            svg.Rect().append("text")
        with pytest.raises(TypeError):
            svg.GlyphRef().append(svg.Rect())
        with pytest.raises(TypeError):
            svg.Group().append(42)  # type: ignore[type-var]
        assert ContentModel.MIXED == ContentModel.TEXT | ContentModel.ELEMENTS

    def test_iteration_and_search(self) -> None:
        root = svg.Svg(svg.Group(svg.Rect(id="a"), svg.Group(svg.Rect(id="b"))), svg.Circle())
        assert [e.tag for e in root.iter()] == ["svg", "g", "rect", "g", "rect", "circle"]
        assert [e.tag for e in root.iter(max_depth=1)] == ["svg", "g", "circle"]
        assert len(root.find_all("rect")) == 2
        assert root.find(svg.Circle) is not None
        assert root.find("ellipse") is None
        b = root.get_element_by_id("b")
        assert b is not None and b.root() is root

    def test_text_property(self) -> None:
        t = svg.Text("Hello ", svg.TSpan("world"))
        assert t.text == "Hello "
        t.text = "Bye "
        assert t.children[0] == "Bye " and isinstance(t.children[1], svg.TSpan)
        assert t.span("!", fill="red").text == "!"

    def test_copy_is_deep_and_detached(self) -> None:
        g = svg.Group(svg.Rect(1, 1, 1, 1), fill="red")
        clone = svg.Svg(g).find(svg.Group).copy()  # type: ignore[union-attr]
        assert clone.parent is None
        clone.find(svg.Rect).set("x", 9)  # type: ignore[union-attr]
        assert g.find(svg.Rect).get("x") == 1  # type: ignore[union-attr]
        assert clone.find(svg.Rect).parent is clone  # type: ignore[union-attr]

    def test_repr(self) -> None:
        assert repr(svg.Circle(1, 2, 3)) == "<Circle circle cx='1' cy='2' r='3'>"

    def test_unknown_element(self) -> None:
        u = UnknownElement("blink", "x", namespace="urn:x")
        assert u.tag == "blink" and u.text == "x"
        assert Element.lookup("blink") is None


class TestStructure:
    def test_svg_root_defaults(self) -> None:
        root = svg.Svg.with_size(100, 50)
        assert root.view_box == svg.ViewBox(0, 0, 100, 50)
        assert root.get("version") == "1.1"
        root.view_box = "0 0 10 10"
        assert root.view_box == svg.ViewBox(0, 0, 10, 10)
        root.view_box = None
        assert root.view_box is None

    def test_defs_created_once(self) -> None:
        root = svg.Svg(svg.Rect())
        assert root.defs() is root.defs()
        assert root[0] is root.defs()

    def test_symbol_use_switch_a(self) -> None:
        sym = svg.Symbol(svg.Circle(5, 5, 5), id="dot", view_box=(0, 0, 10, 10))
        use = svg.Use(sym, 3, 4, width=10)
        assert str(use) == '<use xmlns:xlink="http://www.w3.org/1999/xlink" x="3" y="4" width="10" xlink:href="#dot"/>'
        sw = svg.Switch(svg.Text("fr", system_language="fr"), svg.Text("other"))
        assert len(sw) == 2
        link = svg.A(svg.Rect(), href="https://example.org", target="_blank")
        assert link.get("target") == "_blank"

    def test_descriptive(self) -> None:
        assert str(svg.Title("T")) == "<title>T</title>"
        assert str(svg.Desc("a < b")) == "<desc>a &lt; b</desc>"
        assert str(svg.Title()) == "<title/>"

    def test_style_element_accepts_style_sheet(self) -> None:
        sheet = svg.StyleSheet().rule("rect", fill="red")
        el = svg.StyleElement(sheet)
        assert el.text == "rect { fill:red }"
        el.text = "circle { fill: blue }"
        assert str(el) == '<style type="text/css">circle { fill: blue }</style>'

    def test_external_elements(self) -> None:
        img = svg.Image("pic.png", 0, 0, 10, 10, preserve_aspect_ratio=svg.PreserveAspectRatio(svg.Align.NONE))
        assert 'preserveAspectRatio="none"' in str(img)
        assert str(svg.Script("alert(1)")) == '<script type="text/ecmascript">alert(1)</script>'
        view = svg.View(id="zoom", view_box="0 0 5 5", view_target="r")
        assert 'viewTarget="r"' in str(view)
        cursor = svg.Cursor("hand.png", 2, 3)
        assert str(cursor) == '<cursor xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="hand.png" x="2" y="3"/>'
        profile = svg.ColorProfile("cmyk", "cmyk.icc", rendering_intent="perceptual")
        assert profile.get("rendering-intent") == "perceptual"

    def test_foreign_object(self) -> None:
        div = UnknownElement("div", "hello", namespace="http://www.w3.org/1999/xhtml")
        fo = svg.ForeignObject(div, width=100, height=20)
        text = svg.Svg(fo).to_string()
        node = wellformed(text)
        assert node.find(f"{SVG_NS}foreignObject/{{http://www.w3.org/1999/xhtml}}div") is not None


class TestText:
    def test_positioning_lists(self) -> None:
        t = svg.Text("abc", x=[1, 2, 3], dy=(0, 1), rotate=[10, 20], text_length=30, length_adjust="spacing")
        assert 'x="1 2 3"' in str(t) and 'rotate="10 20"' in str(t) and 'textLength="30"' in str(t)

    def test_text_path_tref_altglyph(self) -> None:
        curve = svg.Path("M0 0 C10 10 20 10 30 0", id="curve")
        tp = svg.TextPath("along", href=curve, start_offset=svg.percent(50), method="align")
        assert str(tp) == '<textPath xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#curve" startOffset="50%" method="align">along</textPath>'
        assert str(svg.TRef("#t")) == '<tref xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#t"/>'
        alt = svg.AltGlyph("x", href="#g", glyph_ref="g1", format="svg")
        assert 'glyphRef="g1"' in str(alt)
        item = svg.AltGlyphItem()
        item.add(svg.GlyphRef("#a", glyph_ref="a"))
        definition = svg.AltGlyphDef(item, id="def")
        assert len(definition) == 1

    def test_mixed_content_stays_inline(self) -> None:
        t = svg.Text("A", svg.TSpan("B", font_weight="bold"), "C")
        assert t.to_string(xml_declaration=False) == '<text>A<tspan font-weight="bold">B</tspan>C</text>\n'


class TestFonts:
    def test_font_with_glyphs_and_kerning(self) -> None:
        font = svg.Font(svg.FontFace(font_family="Box", units_per_em=1000, ascent=800, descent=-200, panose_1="0 0 0 0 0 0 0 0 0 0"), horiz_adv_x=500, id="box")
        font.add(svg.MissingGlyph(d="M0 0 h500 v700 h-500 z"))
        glyph = font.glyph("A", svg.PathBuilder().move_to(0, 0).line_to(250, 700).line_to(500, 0).close(), glyph_name="A")
        font.add(svg.HKern.pair("A", "V", 80))
        assert font.glyphs() == {"A": glyph}
        text = font.to_string(xml_declaration=False, pretty=False)
        assert 'units-per-em="1000"' in text and 'panose-1="0 0 0 0 0 0 0 0 0 0"' in text
        assert '<hkern u1="A" u2="V" k="80"/>' in text
        assert 'horiz-adv-x="500"' in text

    def test_font_face_sources(self) -> None:
        src = svg.FontFaceSrc(svg.FontFaceUri("fonts.svg#box", svg.FontFaceFormat("svg")), svg.FontFaceName("Box Regular"))
        text = str(src)
        assert '<font-face-uri xlink:href="fonts.svg#box"><font-face-format string="svg"/></font-face-uri>' in text
        assert '<font-face-name name="Box Regular"/>' in text


class TestPaintServers:
    def test_gradient_transform_property_override(self) -> None:
        grad = svg.LinearGradient(transform="rotate(45)")
        assert "gradientTransform" in grad.attributes and "transform" not in grad.attributes
        assert grad.transform == Transform().rotate(45)
        pattern = svg.Pattern(width=10, height=10, pattern_units="userSpaceOnUse")
        pattern.transform = Transform().scale(2)
        assert str(pattern.attributes["patternTransform"]) == "scale(2)"
        pattern.transform = None
        assert "patternTransform" not in pattern.attributes
        group = svg.Group(transform="scale(3)")
        assert "transform" in group.attributes

    def test_stops(self) -> None:
        grad = svg.RadialGradient.from_stops([(0, "white"), (1, svg.Color(0, 0, 0), 0.5)], cx=0.5, r=0.5, fx=0.3)
        assert [s.get("offset") for s in grad] == [0, 1]
        assert str(grad[1]) == '<stop offset="1" stop-color="#000000" stop-opacity="0.5"/>'
        horizontal = svg.LinearGradient.horizontal("red", "green", "blue", spread_method="reflect")
        assert [s.get("offset") for s in horizontal] == [0, 0.5, 1]
        assert horizontal.get("spreadMethod") == "reflect"
        assert svg.LinearGradient.vertical("red").get("y2") == 1


class TestClipping:
    def test_clip_mask_marker(self) -> None:
        clip = svg.ClipPath(svg.Circle(5, 5, 5), clip_path_units="objectBoundingBox")
        mask = svg.Mask(svg.Rect(0, 0, 1, 1, fill="white"), mask_units="userSpaceOnUse", x=0, width=10)
        marker = svg.Marker(svg.Path("M0 0 L10 5 L0 10 z"), ref_x=10, ref_y=5, orient="auto", marker_width=4, view_box=(0, 0, 10, 10))
        shape = svg.Path("M0 0 L50 50", clip_path=clip, mask=mask, marker_end=marker)
        assert shape.get("clip-path") == clip.ref
        assert shape.get("mask") == mask.ref
        assert shape.get("marker-end") == marker.ref
        assert 'refX="10"' in str(marker) and 'orient="auto"' in str(marker) and 'viewBox="0 0 10 10"' in str(marker)
        assert 'clipPathUnits="objectBoundingBox"' in str(clip)
