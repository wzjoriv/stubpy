from __future__ import annotations

from pathlib import Path

import pytest

import svgwriter as svg
from svgwriter import builder
from svgwriter.document import ShapeKind

from .conftest import roundtrip, wellformed


class TestDocument:
    def test_group_context_manager_nests(self) -> None:
        doc = svg.Document(100, 100)
        with doc.group(fill="red") as outer:
            doc.add(svg.Rect())
            with doc.group(id="inner") as inner:
                doc.add(svg.Circle())
            doc.add(svg.Line())
        doc.add(svg.Ellipse())
        assert [c.tag for c in outer] == ["rect", "g", "line"]
        assert [c.tag for c in inner] == ["circle"]
        assert doc.current is doc.root
        assert [c.tag for c in doc.root] == ["g", "ellipse"]

    def test_stack_unwinds_on_error(self) -> None:
        doc = svg.Document(10, 10)
        with pytest.raises(RuntimeError), doc.group():
            raise RuntimeError
        assert doc.current is doc.root

    def test_nest_any_container(self) -> None:
        doc = svg.Document(10, 10)
        with doc.nest(svg.A(href="https://example.org")) as link:
            doc.add(svg.Text("go"))
        assert len(link) == 1

    def test_define_title_describe(self) -> None:
        doc = svg.Document(10, 10)
        grad = doc.define(svg.RadialGradient())
        doc.title("T")
        doc.describe("D")
        assert grad.id and grad.parent is doc.defs
        assert doc.root[0].tag == "title"
        assert doc.get_element_by_id(grad.id) is grad
        assert len(list(doc)) == 5

    @pytest.mark.parametrize(
        ("kind", "kwargs", "tag"),
        [
            (ShapeKind.RECT, {"width": 5, "height": 5}, "rect"),
            ("circle", {"r": 3}, "circle"),
            ("ellipse", {"rx": 1, "ry": 2}, "ellipse"),
            ("line", {"x2": 4}, "line"),
            ("polyline", {"points": [(0, 0), (1, 1)]}, "polyline"),
            ("polygon", {"points": [(0, 0), (1, 1), (0, 1)]}, "polygon"),
            ("path", {"d": "M0 0 L1 1"}, "path"),
            ("square", {"size": 4, "fill": "red"}, "rect"),
        ],
    )
    def test_add_shape_dispatch(self, kind: ShapeKind | str, kwargs: dict[str, object], tag: str) -> None:
        doc = svg.Document(10, 10)
        shape = doc.add_shape(kind, **kwargs)
        assert shape.tag == tag and shape.parent is doc.root

    def test_shape_kind_auto_values(self) -> None:
        assert ShapeKind.POLYLINE.value == "polyline"
        with pytest.raises(ValueError):
            svg.Document().add_shape("hexagon")

    def test_writing_context_manager(self, tmp_path: Path) -> None:
        target = tmp_path / "w.svg"
        with svg.Document.writing(target, 20, 20, options=svg.SerializeOptions(pretty=False)) as doc:
            doc.add(svg.Rect(1, 1, 2, 2))
        text = target.read_text(encoding="utf-8")
        assert text.count("\n") == 1
        assert svg.Document.from_file(target).root.find(svg.Rect) is not None

    def test_from_string_requires_svg_root(self) -> None:
        with pytest.raises(ValueError):
            svg.Document.from_string("<rect/>")
        doc = svg.Document.from_string(svg.Document(5, 5).to_string())
        assert doc.root.view_box == svg.ViewBox(0, 0, 5, 5)

    def test_size_without_view_box(self) -> None:
        doc = svg.Document(width=10)
        assert doc.root.get("width") == 10 and doc.root.view_box is None


class TestFunctionalApi:
    def test_constructors_forward_keywords(self) -> None:
        items = [
            builder.rect(0, 0, 1, 1, fill="red"),
            builder.square(0, 0, 3, stroke="blue"),
            builder.circle(1, 1, 1, opacity=0.5),
            builder.ellipse(1, 1, 2, 1, id="e"),
            builder.line(0, 0, 1, 1, stroke_linecap="round"),
            builder.polyline((0, 0), (1, 1), fill="none"),
            builder.polygon((0, 0), (1, 1), (1, 0)),
            builder.path("M0 0 H1", stroke="black"),
            builder.text("hi", 1, 2, font_size=12),
        ]
        group = builder.group(*items, class_="all")
        assert [i.tag for i in group] == ["rect", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text"]
        assert items[1].get("width") == items[1].get("height") == 3
        assert items[8].get("font-size") == 12
        first, second = roundtrip(svg.Svg(group))
        assert first == second

    def test_use_and_gradients(self) -> None:
        target = svg.Circle(id="c")
        assert builder.use(target, 5, 5).get("xlink:href") == svg.IRI("#c")
        assert builder.linear_gradient("red", "blue", vertical=True).get("y2") == 1
        assert len(builder.radial_gradient("red", "green", "blue")) == 3

    def test_partials(self) -> None:
        assert builder.outline(0, 0, 5, 5).get("fill") == "none"
        assert builder.dashed_line(0, 0, 5, 5).get("stroke-dasharray") == (4, 2)
        assert 'stroke-dasharray="4 2"' in str(builder.dashed_line(0, 0, 1, 1))
        assert builder.dot(3, 4).get("r") == 2
        assert builder.dot.func is builder.circle

    def test_document_function(self) -> None:
        doc = builder.document(30, 20, preserve_aspect_ratio="xMinYMin")
        assert doc.root.get("preserveAspectRatio") == "xMinYMin"


class TestRegistry:
    def test_builtin_shapes(self) -> None:
        assert {"star", "polygon", "gear", "arrow"} <= set(svg.SHAPES.names())
        star = svg.SHAPES.get("star")(50, 50, 40, fill="gold")
        assert len(star.points) == 10
        assert star.get("fill") == "gold"
        assert builder.star.__name__ == "star"
        assert builder.star.__wrapped__ is not None  # type: ignore[attr-defined]
        assert len(builder.regular_polygon(0, 0, 5, sides=5).points) == 5
        assert len(builder.gear(0, 0, 10, teeth=8).points) == 32
        assert builder.arrow(0, 0, 10, 0).get("fill") == "none"

    def test_plugin_registration_and_validation(self) -> None:
        @svg.shape_factory("test-bad")
        def bad() -> svg.Element:
            return "nope"  # type: ignore[return-value]

        @svg.shape_factory("test-ok")
        def ok(size: float, **kwargs: object) -> svg.Rect:
            return svg.Rect.square(size, **kwargs)

        assert "test-ok" in svg.SHAPES and len(svg.SHAPES) >= 6
        assert ok(3).get("width") == 3
        with pytest.raises(TypeError):
            bad()
        with pytest.raises(ValueError):
            svg.shape_factory("test-ok")(ok)
        with pytest.raises(KeyError):
            svg.SHAPES.get("nothing")


class TestEffects:
    def test_drop_shadow_is_a_valid_graph(self) -> None:
        shadow = svg.drop_shadow(3, 3, 2, "navy", 0.4, id="shadow")
        results = {p.get("result") for p in shadow.primitives if p.has("result")}
        inputs = {p.get("in") for p in shadow.iter() if p.has("in")} | {p.get("in2") for p in shadow.iter() if p.has("in2")}
        standard = {svg.StandardInput.SOURCE_ALPHA, svg.StandardInput.SOURCE_GRAPHIC}
        assert inputs <= results | standard
        assert shadow.get("x") == "-20%"
        wellformed(svg.Svg(svg.Defs(shadow)).to_string())

    def test_glow_and_marker(self) -> None:
        assert len(builder.glow(4).primitives) == 2
        marker = builder.arrow_marker("red", 8, id="head")
        assert marker.get("orient") == "auto" and marker.view_box == svg.ViewBox(0, 0, 8, 8)

    def test_drawing_decorator(self) -> None:
        @svg.drawing(50, 40, id="pic")
        def picture(doc: svg.Document, color: str, *, radius: float = 5) -> None:
            doc.add(svg.Circle(25, 20, radius, fill=color))

        doc = picture("red", radius=8)
        assert isinstance(doc, svg.Document)
        assert doc.root.id == "pic"
        assert doc.root.find(svg.Circle).get("r") == 8  # type: ignore[union-attr]
        assert picture.__name__ == "picture"
