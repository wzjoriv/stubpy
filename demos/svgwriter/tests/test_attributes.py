from __future__ import annotations

import pytest

from svgwriter.attributes import (
    IRI,
    Align,
    Attr,
    FuncIRI,
    Length,
    MeetOrSlice,
    PreserveAspectRatio,
    Style,
    StyleSheet,
    Unit,
    ViewBox,
    format_value,
    mm,
    parse_func_iri,
    percent,
    px,
    py_name,
    svg_name,
)
from svgwriter.attributes.names import CAMEL_CASE_ATTRIBUTES


@pytest.mark.parametrize(
    ("python", "expected"),
    [
        ("stroke_width", "stroke-width"),
        ("view_box", "viewBox"),
        ("preserve_aspect_ratio", "preserveAspectRatio"),
        ("xlink_href", "xlink:href"),
        ("xml_space", "xml:space"),
        ("class_", "class"),
        ("in_", "in"),
        ("from_", "from"),
        ("std_deviation", "stdDeviation"),
        ("units_per_em", "units-per-em"),
        ("panose_1", "panose-1"),
        ("k1", "k1"),
        ("fill", "fill"),
        ("viewBox", "viewBox"),
        ("xlink:href", "xlink:href"),
    ],
)
def test_svg_name(python: str, expected: str) -> None:
    assert svg_name(python) == expected


@pytest.mark.parametrize("name", sorted(CAMEL_CASE_ATTRIBUTES))
def test_camel_case_round_trip(name: str) -> None:
    assert svg_name(py_name(name)) == name


def test_py_name_keywords() -> None:
    assert py_name("class") == "class_"
    assert py_name("stroke-width") == "stroke_width"
    assert py_name("xlink:href") == "xlink_href"


class TestLength:
    @pytest.mark.parametrize(
        ("text", "value", "unit"),
        [("10", 10.0, Unit.NONE), ("2.5mm", 2.5, Unit.MM), ("-3e1px", -30.0, Unit.PX), ("50%", 50.0, Unit.PERCENT), (".5in", 0.5, Unit.IN)],
    )
    def test_parse(self, text: str, value: float, unit: Unit) -> None:
        assert Length.parse(text) == Length(value, unit)

    def test_parse_passthrough(self) -> None:
        length = Length(1, Unit.EM)
        assert Length.parse(length) is length
        assert Length.parse(3) == Length(3.0)

    @pytest.mark.parametrize("bad", ["", "abc", "10 px px", "5furlongs"])
    def test_parse_rejects(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Length.parse(bad)

    def test_str(self) -> None:
        assert str(Length(2.5, Unit.MM)) == "2.5mm"
        assert str(Length(3)) == "3"
        assert str(percent(50)) == "50%"

    @pytest.mark.parametrize(
        ("length", "pixels"),
        [(Length(1, Unit.IN), 96.0), (Length(72, Unit.PT), 96.0), (Length(25.4, Unit.MM), 96.0), (Length(2, Unit.EM), 32.0), (Length(2, Unit.EX), 16.0), (Length(6, Unit.PC), 96.0), (Length(2.54, Unit.CM), 96.0)],
    )
    def test_to_user_units(self, length: Length, pixels: float) -> None:
        assert length.to_user_units() == pytest.approx(pixels)

    def test_percent_needs_reference(self) -> None:
        with pytest.raises(ValueError):
            percent(50).to_user_units()
        assert percent(50).to_user_units(reference=200) == 100

    def test_arithmetic(self) -> None:
        assert mm(2) + mm(3) == mm(5)
        assert mm(2) + 1 == mm(3)
        assert 2 * px(3) == px(6)
        assert -px(1) == px(-1)
        with pytest.raises(ValueError):
            _ = mm(1) + px(1)

    def test_enum_aliases(self) -> None:
        assert Unit.USER is Unit.NONE
        assert Unit.PIXEL is Unit.PX
        assert Unit("in") is Unit.INCH


class TestViewBox:
    def test_parse_and_format(self) -> None:
        box = ViewBox.parse("0, 0 100 50")
        assert box == ViewBox(0, 0, 100, 50)
        assert box.svg_value() == "0 0 100 50"
        assert box.aspect_ratio == 2

    @pytest.mark.parametrize("bad", ["0 0 10", "0 0 -1 5"])
    def test_rejects(self, bad: str) -> None:
        with pytest.raises(ValueError):
            ViewBox.parse(bad)


class TestPreserveAspectRatio:
    @pytest.mark.parametrize("text", ["none", "xMinYMax slice", "defer xMidYMid", "xMaxYMin"])
    def test_round_trip(self, text: str) -> None:
        assert PreserveAspectRatio.parse(text).svg_value() == text

    def test_defaults(self) -> None:
        par = PreserveAspectRatio()
        assert par.align is Align.CENTER
        assert par.meet_or_slice is MeetOrSlice.MEET
        assert str(par) == "xMidYMid"


class TestStyle:
    def test_parse_and_normalize(self) -> None:
        style = Style("fill: red; stroke-width: 2;", opacity=0.5, stroke_linecap="round")
        assert style["stroke_width"] == "2"
        assert str(style) == "fill:red;stroke-width:2;opacity:0.5;stroke-linecap:round"

    def test_none_deletes(self) -> None:
        style = Style(fill="red")
        style["fill"] = None
        assert len(style) == 0

    def test_presentation_only(self) -> None:
        style = Style({"fill": "red", "cursor-x": "1"})
        assert dict(style.presentation_only()) == {"fill": "red"}

    def test_style_sheet(self) -> None:
        sheet = StyleSheet().rule(".a", fill="red").rule("#b", {"stroke": "blue"}, stroke_width=2)
        assert len(sheet) == 2
        assert sheet.css() == ".a { fill:red }\n#b { stroke:blue;stroke-width:2 }"


class TestReferences:
    def test_iri(self) -> None:
        assert str(IRI.local("x")) == "#x"
        assert IRI("file.svg#y").fragment == "y"
        assert IRI("file.svg").fragment is None

    def test_func_iri(self) -> None:
        assert str(FuncIRI("#g")) == "url(#g)"
        assert parse_func_iri("url( '#g' )") == FuncIRI("#g")
        assert parse_func_iri("red") is None


class TestFormatValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1, "1"),
            (1.0, "1"),
            (0.1 + 0.2, "0.3"),
            (-0.00001, "0"),
            (1 / 3, "0.3333"),
            (True, "true"),
            (float("inf"), "indefinite"),
            ((1, 2, 3), "1 2 3"),
            ([(1, 2), (3, 4)], "1,2 3,4"),
            (Unit.MM, "mm"),
            ({"fill": "red"}, "fill:red"),
        ],
    )
    def test_values(self, value: object, expected: str) -> None:
        assert format_value(value) == expected

    def test_precision(self) -> None:
        assert format_value(3.14159265, 2) == "3.14"

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            format_value(float("nan"))
        with pytest.raises(ValueError):
            format_value(float("-inf"))


def test_attr_descriptor_on_class_returns_itself() -> None:
    from svgwriter import Rect

    assert isinstance(Rect.x, Attr)
    assert Rect.x.key == "x"
    assert repr(Rect.width) == "Attr('width')"
