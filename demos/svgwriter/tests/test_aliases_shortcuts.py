from __future__ import annotations

import builtins
import re

import pytest

import svgwriter as svg
from svgwriter import aliases
from svgwriter.elements import Element, ElementFactory, GraphicsContainer

from .conftest import roundtrip, wellformed

SHORTCUTS_PLACED = {
    "rect": ((0, 0, 4, 4), {"rx": 1}, svg.Rect),
    "circle": ((1, 1, 2), {"fill": "red"}, svg.Circle),
    "ellipse": ((1, 1, 2, 3), {}, svg.Ellipse),
    "line": ((0, 0, 4, 4), {"stroke": "black"}, svg.Line),
    "polyline": (([(0, 0), (1, 1)],), {}, svg.Polyline),
    "polygon": (([(0, 0), (1, 1), (1, 0)],), {}, svg.Polygon),
    "path": (("M0 0 H4",), {"stroke_width": 2}, svg.Path),
    "text": (("hi",), {"x": 3, "y": 4}, svg.Text),
    "group": ((), {"opacity": 0.5}, svg.Group),
    "link": ((), {"href": "https://example.org"}, svg.A),
    "switch": ((), {}, svg.Switch),
    "use": (("#x",), {"x": 1}, svg.Use),
    "image": (("pic.png", 0, 0, 10, 10), {}, svg.Image),
}
SHORTCUTS_DEFINED = {
    "linear_gradient": ((svg.Stop(0, "red"),), {"x2": 1}, svg.LinearGradient),
    "radial_gradient": ((), {"r": 0.5}, svg.RadialGradient),
    "pattern": ((), {"width": 4, "height": 4}, svg.Pattern),
    "clip_path": ((), {"clip_path_units": "userSpaceOnUse"}, svg.ClipPath),
    "mask": ((), {}, svg.Mask),
    "marker": ((), {"ref_x": 2, "orient": "auto"}, svg.Marker),
    "filter": ((svg.FeGaussianBlur(2),), {}, svg.Filter),
    "symbol": ((), {"view_box": (0, 0, 4, 4)}, svg.Symbol),
}


def _snake(name: str) -> str:
    special = {"TSpan": "tspan", "TRef": "tref", "MPath": "mpath", "HKern": "hkern", "VKern": "vkern", "Svg": "svg", "StyleElement": "style_element"}
    return special.get(name) or re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class TestAliases:
    def test_every_registered_class_has_a_lowercase_alias(self) -> None:
        for cls in Element.registered().values():
            alias = _snake(cls.__name__)
            assert getattr(svg, alias) is cls, alias
            assert getattr(aliases, alias) is cls

    def test_all_exports_skip_builtin_names(self) -> None:
        assert "circle" in svg.__all__ and "linear_gradient" in svg.__all__ and "fe_gaussian_blur" in svg.__all__
        assert "filter" not in svg.__all__ and "set" not in svg.__all__
        assert svg.filter is svg.Filter and svg.set is svg.Set
        namespace: dict[str, object] = {}
        exec("from svgwriter import *", namespace)
        assert "filter" not in namespace and builtins.set is set

    def test_alias_builds_elements(self) -> None:
        group = svg.group(svg.circle(1, 2, 3), svg.rect(0, 0, 1, 1), svg.linear_gradient())
        assert [c.tag for c in group] == ["circle", "rect", "linearGradient"]
        assert svg.path is svg.Path and svg.svg is svg.Svg and svg.a is svg.A

    def test_subpackage_still_importable_under_alias_name(self) -> None:
        from svgwriter.path import PathBuilder

        assert PathBuilder().move_to(0, 0).build()


class TestDocumentShortcuts:
    @pytest.mark.parametrize("name", sorted(SHORTCUTS_PLACED))
    def test_placed_shortcut(self, name: str) -> None:
        args, kwargs, cls = SHORTCUTS_PLACED[name]
        doc = svg.Document(10, 10)
        element = getattr(doc, name)(*args, **kwargs)
        assert type(element) is cls and element.parent is doc.root
        expected = cls(*args, **kwargs)
        assert element.attributes == expected.attributes

    @pytest.mark.parametrize("name", sorted(SHORTCUTS_DEFINED))
    def test_defined_shortcut(self, name: str) -> None:
        args, kwargs, cls = SHORTCUTS_DEFINED[name]
        doc = svg.Document(10, 10)
        element = getattr(doc, name)(*args, **kwargs)
        assert type(element) is cls and element.parent is doc.defs and element.id
        assert doc.root[0] is doc.defs
        wellformed(doc.to_string())

    def test_shortcut_errors_come_from_the_constructor(self) -> None:
        with pytest.raises(TypeError):
            svg.Document().circle(1, 2, 3, 4)

    def test_with_nesting_on_returned_containers(self) -> None:
        doc = svg.Document(50, 50)
        with doc.group(id="outer") as outer:
            doc.rect(0, 0, 5, 5)
            with outer.group(id="inner") as inner:
                doc.circle(1, 1, 1)
                inner.line(0, 0, 1, 1)
            doc.ellipse(1, 1, 1, 1)
        doc.text("after")
        assert [c.tag for c in outer] == ["rect", "g", "ellipse"]
        assert [c.tag for c in inner] == ["circle", "line"]
        assert [c.tag for c in doc.root] == ["g", "text"]

    def test_definition_used_as_context(self) -> None:
        doc = svg.Document(20, 20)
        with doc.clip_path() as clip:
            doc.circle(10, 10, 8)
        doc.rect(0, 0, 20, 20, clip_path=clip)
        assert clip.parent is doc.defs and clip[0].tag == "circle"
        assert doc.root.find(svg.Rect).get("clip-path") == clip.ref  # type: ignore[union-attr]

    def test_with_on_detached_container_is_harmless(self) -> None:
        with svg.Group() as group:
            group.circle(1, 1, 1)
        assert len(group) == 1

    def test_style_and_document_text_shortcuts(self) -> None:
        doc = svg.Document(10, 10)
        doc.title("T")
        sheet = doc.style(svg.StyleSheet().rule("rect", fill="red"))
        assert doc.root.children[1] is sheet
        assert str(doc).startswith("<svg") and doc._repr_svg_() == str(doc)

    def test_shortcuts_work_on_every_graphics_container(self) -> None:
        for cls in (svg.Group, svg.Defs, svg.Symbol, svg.Switch, svg.A, svg.ClipPath, svg.Mask, svg.Marker, svg.Pattern, svg.Svg):
            container = cls()
            assert isinstance(container, GraphicsContainer) and isinstance(container, ElementFactory)
            dot = container.circle(1, 1, 1)
            assert dot.parent is container

    def test_container_definitions_go_to_root_defs(self) -> None:
        doc = svg.Document(10, 10)
        group = doc.group()
        grad = group.linear_gradient()
        assert grad.parent is doc.defs
        loose = svg.Group()
        local = loose.radial_gradient()
        assert local.parent is loose.definitions() and loose[0].tag == "defs"
        defs = svg.Defs()
        assert defs.marker().parent is defs

    def test_container_text_shortcut_replaces_property(self) -> None:
        group = svg.Group()
        label = group.text("hello", x=1)
        assert label.text == "hello" and label.parent is group

    def test_document_is_round_trippable(self) -> None:
        doc = svg.Document(30, 30)
        sky = doc.linear_gradient(svg.Stop(0, "white"), svg.Stop(1, "blue"), x2=0, y2=1)
        doc.rect(0, 0, 30, 30, fill=sky)
        doc.polygon([(0, 0), (5, 5), (0, 5)])
        first, second = roundtrip(doc.root)
        assert first == second
