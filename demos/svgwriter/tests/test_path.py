from __future__ import annotations

import math

import pytest

from svgwriter.path import (
    ArcTo,
    BBox,
    ClosePath,
    CurveTo,
    HLineTo,
    LineTo,
    MoveTo,
    PathBuilder,
    PathData,
    PathSyntaxError,
    QuadTo,
    SmoothCurveTo,
    SmoothQuadTo,
    VLineTo,
    endpoint_to_center,
    parse_path,
)
from svgwriter.transform import Point

ALL_COMMANDS = "M10,20 l5-5 h3 v.5.5 C1 2 3 4 5 6 s1 1 2 2 Q1 1 2 2 t3 3 a5 5 30 1 0 10 10 z m1 1 2 2 L4 4 H1 V2 c1 1 1 1 1 1 S1 1 1 1 q1 1 1 1 T1 1 A1 1 0 0 1 3 3 Z"


def test_parse_all_command_types() -> None:
    kinds = {type(c) for c in parse_path(ALL_COMMANDS)}
    assert kinds == {MoveTo, LineTo, HLineTo, VLineTo, CurveTo, SmoothCurveTo, QuadTo, SmoothQuadTo, ArcTo, ClosePath}


def test_implicit_lineto_after_moveto() -> None:
    commands = parse_path("m1 1 2 2 3 3")
    assert commands == [MoveTo(1, 1, relative=True), LineTo(2, 2, relative=True), LineTo(3, 3, relative=True)]


def test_compact_arc_flags() -> None:
    (arc,) = parse_path("M0 0a5 5 0 1010 10")[1:]
    assert arc == ArcTo(5, 5, 0, True, False, 10, 10, relative=True)


def test_number_forms() -> None:
    d = PathData("M-1.5e1-.5L.5.5")
    assert d[0] == MoveTo(-15, -0.5)
    assert d[1] == LineTo(0.5, 0.5)


@pytest.mark.parametrize("bad", ["L1 1", "M1", "M1 1 X", "M0 0 A1 1 0 2 0 1 1", "M 0 0 L 1"])
def test_syntax_errors(bad: str) -> None:
    with pytest.raises(PathSyntaxError):
        PathData(bad)


def test_empty() -> None:
    assert len(PathData("")) == 0
    assert PathData("").bbox is None


def test_serialize_round_trip() -> None:
    d = PathData(ALL_COMMANDS)
    assert PathData(str(d)) == d
    assert PathData(d.svg_value(compact=True)) == d


def test_compact_form() -> None:
    d = PathData("M10 20 L30 40 L50 60 l-1 -0.5 Z")
    assert d.svg_value(compact=True) == "M10 20 30 40 50 60l-1-.5Z"


def test_to_absolute() -> None:
    d = PathData("M10 10 h10 v10 l-5 5 z m5 5 c1 1 2 2 3 3")
    assert str(d.to_absolute()) == "M10 10 H20 V20 L15 25 Z M15 15 C16 16 17 17 18 18"


def test_normalized_reflects_smooth_controls() -> None:
    d = PathData("M0 0 C0 10 10 10 10 0 S20 -10 20 0").normalized()
    assert d[2] == CurveTo(10, -10, 20, -10, 20, 0)
    q = PathData("M0 0 Q5 10 10 0 T20 0").normalized()
    assert q[2] == QuadTo(15, -10, 20, 0)


def test_bbox_lines_and_curves() -> None:
    assert PathData("M0 0 h10 v10 z").bbox == BBox(0, 0, 10, 10)
    bbox = PathData("M0 0 Q5 10 10 0").bbox
    assert bbox is not None
    assert bbox.height == pytest.approx(5, abs=0.05)


def test_arc_center_conversion() -> None:
    arc = endpoint_to_center(Point(0, 0), Point(10, 0), 5, 5, 0, False, True)
    assert arc is not None
    assert (arc.cx, arc.cy) == pytest.approx((5, 0))
    assert abs(arc.sweep) == pytest.approx(math.pi)
    assert arc.point_at(1) == pytest.approx(Point(10, 0))
    mid = arc.point_at(0.5)
    assert mid.y == pytest.approx(-5)


def test_arc_radius_scaling_and_degenerate() -> None:
    arc = endpoint_to_center(Point(0, 0), Point(10, 0), 1, 1, 0, False, False)
    assert arc is not None and arc.rx == pytest.approx(5)
    assert endpoint_to_center(Point(0, 0), Point(0, 0), 1, 1, 0, False, False) is None
    assert endpoint_to_center(Point(0, 0), Point(1, 0), 0, 1, 0, False, False) is None


def test_circle_bbox_via_builder() -> None:
    bbox = PathBuilder().circle(50, 50, 10).build().bbox
    assert bbox is not None
    assert (bbox.x, bbox.y, bbox.width, bbox.height) == pytest.approx((40, 40, 20, 20), abs=0.1)


def test_builder_chaining_and_relative() -> None:
    b = PathBuilder((0, 0)).line_to(10, 0).vertical_to(5, relative=True).horizontal_to(-10, relative=True)
    b.curve_to(1, 1, 2, 2, 3, 3).smooth_curve_to(4, 4, 5, 5).quad_to(6, 6, 7, 7).smooth_quad_to(8, 8).close()
    assert str(b) == "M0 0 L10 0 v5 h-10 C1 1 2 2 3 3 S4 4 5 5 Q6 6 7 7 T8 8 Z"
    assert b.current_point == Point(0, 0)
    assert len(b) == 9


def test_builder_regular_polygon() -> None:
    d = PathBuilder().regular_polygon(0, 0, 10, 4).build()
    assert len(d) == 5
    assert d[0].end_point(Point(0, 0), Point(0, 0)) == pytest.approx(Point(0, -10))
    with pytest.raises(ValueError):
        PathBuilder().regular_polygon(0, 0, 1, 2)


def test_builder_extend_and_to_element() -> None:
    path = PathBuilder().extend("M0 0 L1 1").to_element(stroke="red")
    assert path.tag == "path"
    assert str(path) == '<path stroke="red" d="M0 0 L1 1"/>'


def test_pathdata_sequence_protocol() -> None:
    d = PathData("M0 0 L1 1 L2 2")
    assert isinstance(d[1:], PathData)
    assert d + PathData([ClosePath()]) == PathData("M0 0 L1 1 L2 2 Z")
    assert hash(d) == hash(PathData("M0 0 L1 1 L2 2"))
    assert repr(d) == "PathData('M0 0 L1 1 L2 2')"
