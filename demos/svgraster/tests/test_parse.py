"""Parser tests: path data, transforms, colors, units, CSS and viewports."""
from __future__ import annotations


import numpy as np
import pytest

from svgraster.dom import Document, Matrix, parse_color, parse_length, parse_transform
from svgraster.dom.color import Color
from svgraster.dom.css import Stylesheet, parse_declarations, parse_selector
from svgraster.dom.units import UnitContext, parse_length_list
from svgraster.parse import (
    AspectRatio,
    PathSyntaxError,
    ViewBox,
    arc_center,
    flatten_path,
    parse_aspect_ratio,
    parse_path,
    parse_viewbox,
    rect_path,
    tokenize,
    viewbox_transform,
)
from tests.conftest import svg


class TestPathData:
    def test_compact_numbers_and_implicit_lineto(self):
        path = parse_path("M1.5.5-2-3 4e1,5")
        assert path.segments == [("M", 1.5, 0.5), ("L", -2.0, -3.0), ("L", 40.0, 5.0)]

    def test_relative_commands_and_shorthands(self):
        path = parse_path("m10 10 h5 v5 H0 V0 z")
        assert path.segments == [("M", 10, 10), ("L", 15, 10), ("L", 15, 15), ("L", 0, 15), ("L", 0, 0), ("Z",)]

    def test_smooth_curves_reflect_control_points(self):
        path = parse_path("M0 0 C 1 1 2 1 3 0 S 5 -1 6 0 Q 7 1 8 0 T 10 0")
        assert path.segments[2] == ("C", 4.0, -1.0, 5.0, -1.0, 6.0, 0.0)
        assert path.segments[4] == ("Q", 9.0, -1.0, 10.0, 0.0)

    def test_arc_flags_without_separators(self):
        path = parse_path("M0 0a5 5 0 1010 0")
        assert path.segments[1] == ("A", 5.0, 5.0, 0.0, True, False, 10.0, 0.0)

    def test_relative_move_after_close_uses_subpath_start(self):
        path = parse_path("M10 10 l5 0 z m1 1 l1 0")
        assert path.segments[3] == ("M", 11.0, 11.0)

    def test_error_keeps_valid_prefix(self):
        path = parse_path("M0 0 L10 10 L5 x")
        assert path.segments == [("M", 0.0, 0.0), ("L", 10.0, 10.0)]
        with pytest.raises(PathSyntaxError):
            parse_path("M0 0 L10 10 L5 x", strict=True)

    def test_must_start_with_moveto(self):
        with pytest.raises(PathSyntaxError):
            tokenize("L 1 1")

    def test_flatten_closed_and_open_subpaths(self):
        lines = flatten_path(parse_path("M0 0 L10 0 L10 10 Z M20 20 L30 30"))
        assert [p.closed for p in lines] == [True, False]
        assert lines[0].points.shape == (3, 2)

    def test_lone_moveto_is_dropped(self):
        assert flatten_path(parse_path("M5 5")) == []

    def test_flattened_circle_arc_stays_on_circle(self):
        lines = flatten_path(parse_path("M10 0 A10 10 0 0 1 -10 0"), tolerance=0.01)
        radii = np.hypot(lines[0].points[:, 0], lines[0].points[:, 1])
        assert np.allclose(radii, 10.0)
        assert lines[0].points[:, 1].max() > 9.99

    def test_arc_radius_scaled_up_when_too_small(self):
        cx, cy, rx, ry, *_ = arc_center(0, 0, 1, 1, 0, False, True, 10, 0)
        assert (cx, cy) == pytest.approx((5.0, 0.0)) and rx == pytest.approx(5.0)

    def test_rounded_rect_has_arcs(self):
        kinds = [s[0] for s in rect_path(0, 0, 10, 10, 2, 2).segments]
        assert kinds.count("A") == 4


class TestTransforms:
    def test_transform_list_composes_left_to_right(self):
        m = parse_transform("translate(10,20) scale(2)")
        assert m.apply(1, 1) == (12.0, 22.0)

    def test_rotate_about_point(self):
        x, y = parse_transform("rotate(90 5 5)").apply(10, 5)
        assert (x, y) == pytest.approx((5.0, 10.0))

    def test_skew_and_matrix(self):
        assert parse_transform("skewX(45)").apply(0, 1) == pytest.approx((1.0, 1.0))
        assert parse_transform("matrix(1 0 0 1 3 4)") == Matrix.translate(3, 4)

    def test_inverse(self):
        m = parse_transform("rotate(30) scale(2 3) translate(4 5)")
        x, y = m.inverse().apply(*m.apply(1.5, -2.0))
        assert (x, y) == pytest.approx((1.5, -2.0))


class TestColors:
    @pytest.mark.parametrize("text, expected", [
        ("red", (255, 0, 0, 255)),
        ("#0f08", (0, 255, 0, 136)),
        ("#336699", (51, 102, 153, 255)),
        ("rgb(10%, 20%, 30%)", (26, 51, 76, 255)),
        ("rgba(255,0,0,0.5)", (255, 0, 0, 128)),
        ("hsl(120, 100%, 25%)", (0, 128, 0, 255)),
        ("transparent", (0, 0, 0, 0)),
        ("LightGoldenRodYellow", (250, 250, 210, 255)),
    ])
    def test_css_colors(self, text, expected):
        assert parse_color(text).to_bytes() == expected

    def test_current_color_and_invalid(self):
        assert parse_color("currentColor", Color(0.1, 0.2, 0.3)) == Color(0.1, 0.2, 0.3)
        assert parse_color("notacolor") is None
        assert parse_color("#12") is None


class TestUnitsAndCss:
    def test_absolute_units(self):
        assert parse_length("1in") == 96.0
        assert parse_length("72pt") == pytest.approx(96.0)
        assert parse_length("25.4mm") == pytest.approx(96.0)

    def test_relative_units(self):
        ctx = UnitContext(font_size=10, viewport_width=200, viewport_height=100)
        assert parse_length("2em", ctx) == 20.0
        assert parse_length("50%", ctx, "x") == 100.0
        assert parse_length("50%", ctx, "y") == 50.0

    def test_dash_list(self):
        assert parse_length_list("5, 2 1") == [5.0, 2.0, 1.0]
        assert parse_length_list("none") == []

    def test_declarations_and_important(self):
        decls = parse_declarations("fill: red; stroke : blue !important; /* c */ bad")
        assert [(d.name, d.value, d.important) for d in decls] == [("fill", "red", False), ("stroke", "blue", True)]

    def test_selector_specificity(self):
        assert parse_selector("g > rect.a#b").specificity == 112
        assert parse_selector("a:hover") is None

    def test_cascade_order(self):
        doc = Document.parse(svg(
            "<style>rect{fill:green} .c{fill:blue} #r{fill:yellow} g rect{stroke:red}"
            "@media print{rect{fill:black}}</style>"
            '<g fill="purple"><rect id="r" class="c" fill="orange" style="opacity:0.5"/>'
            '<rect class="c"/><circle/></g>'))
        rect, rect2, circle = doc.root.children[1].children
        assert rect.style["fill"] == "yellow" and rect.style["stroke"] == "red"
        assert rect.style["opacity"] == "0.5"
        assert rect2.style["fill"] == "blue"
        assert circle.style["fill"] == "purple"

    def test_inherit_keyword_and_non_inherited(self):
        doc = Document.parse(svg('<g opacity="0.5" stroke="red"><rect opacity="inherit" stroke-width="inherit"/></g>'))
        rect = doc.root.children[0].children[0]
        assert rect.style["opacity"] == "0.5" and rect.style["stroke"] == "red"

    def test_style_sheet_object(self):
        sheet = Stylesheet()
        sheet.extend("rect, circle { fill: red }")
        assert len(sheet.rules) == 2


class TestViewport:
    def test_viewbox_and_aspect_ratio(self):
        box = parse_viewbox("0 0 10 20")
        assert box == ViewBox(0, 0, 10, 20)
        assert parse_viewbox("0 0 -1 5") is None
        m = viewbox_transform(box, 100, 100, parse_aspect_ratio("xMidYMid meet"))
        assert m.apply(0, 0) == pytest.approx((25.0, 0.0))
        m = viewbox_transform(box, 100, 100, parse_aspect_ratio("xMinYMin slice"))
        assert m.apply(10, 20) == pytest.approx((100.0, 200.0))

    def test_aspect_none(self):
        assert parse_aspect_ratio("none") == AspectRatio(None, None, False)
        m = viewbox_transform(ViewBox(0, 0, 10, 20), 100, 100, parse_aspect_ratio("none"))
        assert m.axis_scales == pytest.approx((10.0, 5.0))

    def test_document_rejects_non_svg_root(self):
        with pytest.raises(ValueError):
            Document.parse("<html/>")
        with pytest.raises(ValueError):
            Document.parse("<svg")

    def test_href_chain(self):
        doc = Document.parse(svg('<linearGradient id="a" href="#b"/><linearGradient id="b" xlink:href="#a"/>'))
        assert [n.id for n in doc.href_chain(doc.ids["a"])] == ["a", "b"]
