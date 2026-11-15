from __future__ import annotations

import math
import warnings

import pytest

import svgwriter as svg
from svgwriter import ops
from svgwriter.ops import _skia
from svgwriter.path import PathData

needs_skia = pytest.mark.skipif(not ops.available(), reason="skia-python is not installed")
FONT = "Arial, DejaVu Sans, Liberation Sans, sans-serif"


@pytest.fixture
def no_skia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_skia, "_load", lambda: None)


class TestWithoutSkia:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: svg.Circle(0, 0, 1) | svg.Rect(0, 0, 1, 1),
            lambda: svg.Circle(0, 0, 1) & svg.Rect(0, 0, 1, 1),
            lambda: svg.Circle(0, 0, 1) - svg.Rect(0, 0, 1, 1),
            lambda: svg.Circle(0, 0, 1) ^ svg.Rect(0, 0, 1, 1),
            lambda: svg.Circle(0, 0, 1).total_length(),
            lambda: svg.Circle(0, 0, 1).point_at_length(1),
            lambda: svg.Circle(0, 0, 1).contains_point(0, 0),
            lambda: svg.Circle(0, 0, 1).exact_bbox(),
            lambda: svg.Circle(0, 0, 1).simplified(),
            lambda: svg.Circle(0, 0, 1).stroked(2),
            lambda: svg.text_to_path("Hi"),
            lambda: ops.text_width("Hi"),
            lambda: ops.rasterize(svg.Document(5, 5)),
        ],
    )
    def test_clear_error(self, no_skia: None, call: object) -> None:
        with pytest.raises(svg.MissingDependencyError, match=r"svgwriter\[ops\]"):
            call()  # type: ignore[operator]
        assert not ops.available()

    def test_error_is_an_import_error(self) -> None:
        assert issubclass(svg.MissingDependencyError, ImportError)

    def test_bad_geometry_type(self) -> None:
        with pytest.raises(TypeError, match="expected a shape"):
            _skia.geometry_data(5)  # type: ignore[arg-type]

    def test_operators_reject_non_geometry(self) -> None:
        with pytest.raises(TypeError):
            _ = svg.Circle() | 5  # type: ignore[operator]
        with pytest.raises(TypeError):
            _ = svg.Circle() - 5  # type: ignore[operator]


@needs_skia
class TestBooleanOps:
    def test_operators_return_paths(self) -> None:
        a = svg.Circle(50, 50, 40, fill="red", id="a")
        b = svg.Rect(50, 0, 60, 100)
        for result in (a | b, a & b, a - b, a ^ b):
            assert isinstance(result, svg.Path) and len(result.d) > 2
            assert result.get("fill") == "red" and result.id is None
        assert (a | b).exact_bbox() == svg.BBox(10, 0, 100, 100)
        assert (a & b).exact_bbox() == svg.BBox(50, 10, 40, 80)
        assert (a - b).exact_bbox() == svg.BBox(10, 10, 40, 80)

    def test_reflected_operators_with_path_data(self) -> None:
        square = PathData("M0 0 H10 V10 H0 Z")
        circle = svg.Circle(10, 10, 5, fill="blue")
        assert isinstance(square | circle, svg.Path)
        assert isinstance(square & circle, svg.Path)
        assert (square - circle).contains_point(1, 1)
        assert not (square - circle).contains_point(9, 9)
        assert isinstance("M0 0 H10 V10 H0 Z" ^ circle, svg.Path)

    def test_in_place_operators_on_paths(self) -> None:
        p = svg.Path("M0 0 H10 V10 H0 Z", transform="translate(5)")
        same = p
        p |= svg.Rect(10, 0, 10, 10)
        assert p is same and not p.has("transform")
        assert p.exact_bbox() == svg.BBox(5, 0, 15, 10)
        p -= svg.Rect(5, 0, 5, 10)
        p &= svg.Rect(0, 0, 18, 10)
        p ^= svg.Rect(12, 0, 2, 10)
        assert p.exact_bbox() == svg.BBox(10, 0, 8, 10)

    def test_union_of_many_and_methods(self) -> None:
        dots = [svg.Circle(x, 0, 1) for x in range(0, 10, 3)]
        merged = dots[0].union(*dots[1:])
        assert len(merged.d.subpaths()) == 4
        assert dots[0].intersection(dots[1]).d == PathData()
        assert len(ops.union(dots[0]).subpaths()) == 1
        assert ops.xor(dots[0], dots[0]) == PathData()

    def test_transforms_and_fill_rule_are_honoured(self) -> None:
        moved = svg.Rect(0, 0, 10, 10, transform="translate(100)")
        assert (moved | svg.Rect(100, 0, 1, 1)).exact_bbox().x == 100
        donut = svg.Path("M0 0 H10 V10 H0 Z M2 2 H8 V8 H2 Z", fill_rule="evenodd")
        assert not donut.contains_point(5, 5) and donut.contains_point(1, 1)
        merged = donut | svg.Rect(20, 0, 1, 1)
        assert not merged.has("fill-rule") and not merged.contains_point(5, 5)

    def test_text_outlines_take_part(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            label = svg.Text("H", x=10, y=50, font_size=40, font_family=FONT)
            stencil = svg.Rect(0, 0, 60, 60, fill="black") - label
            assert isinstance(stencil, svg.Path)
            assert stencil.exact_bbox() == svg.BBox(0, 0, 60, 60)
            assert len(stencil.d.subpaths()) >= 2
            assert label.to_path().exact_bbox().width > 0


@needs_skia
class TestMeasurement:
    def test_length_and_points(self) -> None:
        circle = svg.Circle(0, 0, 10)
        assert math.isclose(circle.total_length(), 2 * math.pi * 10, rel_tol=1e-3)
        start = circle.point_at_length(0)
        assert math.isclose(start.x, -10) and math.isclose(start.y, 0, abs_tol=1e-6)
        line = svg.Path("M0 0 H10 M0 5 H10")
        assert line.total_length() == 20
        assert line.point_at_length(15) == svg.Point(5, 5)
        assert line.point_at_length(100) == svg.Point(10, 5)
        assert ops.tangent_at_length(line, 2) == svg.Point(1, 0)

    def test_zero_length(self) -> None:
        with pytest.raises(ValueError, match="zero length"):
            ops.point_at_length(PathData("M0 0"), 1)

    def test_bounds_are_exact_for_curves(self) -> None:
        circle = svg.Circle(5, 5, 5)
        assert circle.exact_bbox() == svg.BBox(0, 0, 10, 10)
        assert ops.bounds("M0 0 C0 10 10 10 10 0").height == pytest.approx(7.5)

    def test_contains(self) -> None:
        assert svg.Rect(0, 0, 5, 5).contains_point(1, 1)
        assert not svg.Rect(0, 0, 5, 5, transform="translate(10)").contains_point(1, 1)

    def test_simplify(self) -> None:
        bow = svg.Path("M0 0 L10 10 L10 0 L0 10 Z", fill="green")
        simple = bow.simplified()
        assert simple.get("fill") == "green" and len(simple.d.subpaths()) == 2

    def test_stroke_to_path(self) -> None:
        line = svg.Line(0, 0, 10, 0, stroke="red", stroke_width=4, stroke_linecap="round")
        outline = line.stroked()
        assert outline.get("fill") == "red" and not outline.has("stroke")
        assert outline.exact_bbox() == svg.BBox(-2, -2, 14, 4)
        assert ops.bounds(ops.stroke_to_path(line, 2, cap="butt")) == svg.BBox(0, -1, 10, 2)
        assert line.stroked(2, cap="square", join="bevel", miter_limit=2).exact_bbox().width == 12


@needs_skia
class TestText:
    def test_text_to_path(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            path = svg.text_to_path("Hello", FONT, 24, fill="navy", x=10, y=40)
        assert isinstance(path, svg.Path) and path.get("fill") == "navy"
        box = path.exact_bbox()
        assert 10 <= box.x < 14 and box.y < 40 and box.y + box.height <= 41

    def test_anchor_weight_italic(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            start = ops.bounds(ops.text_outline("Mid", FONT, 20, anchor="start"))
            middle = ops.bounds(ops.text_outline("Mid", FONT, 20, anchor="middle"))
            end = ops.bounds(ops.text_outline("Mid", FONT, 20, anchor="end"))
            assert start.x > middle.x > end.x
            regular = ops.text_width("Wide", FONT, 20)
            bold = ops.text_width("Wide", FONT, 20, weight="bold")
            assert bold >= regular > 0
            assert ops.text_width("x", FONT, 20, weight=300, italic=True) > 0

    def test_unknown_font_warns_and_falls_back(self) -> None:
        with pytest.warns(UserWarning, match="not found"):
            data = ops.text_outline("A", "No Such Font Family 123", 20)
        assert len(data) > 0

    def test_empty_text(self) -> None:
        assert ops.text_outline("", "sans-serif") == PathData()


@needs_skia
class TestRasterize:
    def test_png_output(self) -> None:
        doc = svg.Document(20, 10)
        doc.rect(0, 0, 20, 10, fill="red")
        png = ops.rasterize(doc, scale=2, background="white")
        assert png.startswith(b"\x89PNG") and int.from_bytes(png[16:20], "big") == 40

    def test_size_fallbacks(self) -> None:
        assert ops.rasterize(svg.Document(root=svg.Svg(view_box=(0, 0, 7, 3)))).startswith(b"\x89PNG")
        assert int.from_bytes(ops.rasterize(svg.Document(root=svg.Svg()))[16:20], "big") == 300
