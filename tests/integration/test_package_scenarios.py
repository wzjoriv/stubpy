"""End-to-end stubs for class hierarchies spread over the modules of one package."""
from __future__ import annotations

import re

import pytest

from tests.conftest import assert_valid_syntax, flatten


def _section(content: str, name: str) -> str:
    """Return the stub text of class *name* up to the next class."""
    return content.split(f"class {name}")[1].split("\nclass ")[0]


def _def_line(section: str, prefix: str) -> str:
    """Return the flattened signature line of *section* that contains *prefix*."""
    lines = [l for l in flatten(section).splitlines() if prefix in l]
    assert lines, f"{prefix!r} not found"
    return lines[0]


def _imports_name(header: str, module: str, name: str) -> bool:
    """True when *header* has a ``from <module> import ...`` line binding *name*."""
    pattern = rf"^from {re.escape(module)} import .*\b{re.escape(name)}\b"
    return re.search(pattern, header, re.MULTILINE) is not None


class TestElementStub:
    @pytest.fixture(autouse=True)
    def setup(self, element_stub):
        self.c = element_stub

    def test_both_classes_present(self):
        assert "class Style:" in self.c
        assert "class Element(ABC):" in self.c

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_style_open_kwargs_preserved(self):
        assert "**props: Any" in _section(self.c, "Style")

    def test_style_classmethod(self):
        s = _section(self.c, "Style")
        assert "@classmethod" in s
        assert "def from_dict(cls, data: dict[str, Any]) -> Style:" in s

    def test_style_dunder_methods(self):
        s = _section(self.c, "Style")
        assert "def __setitem__" in s
        assert "def __getitem__" in s

    def test_element_init_params(self):
        init = _def_line(_section(self.c, "Element"), "def __init__")
        assert "id: str | None" in init
        assert "title: str | None" in init
        assert "opacity: float" in init
        assert "-> None" in init

    def test_element_transform_methods(self):
        assert "def translate(self, tx: float, ty: float = 0.0) -> Element:" in self.c
        assert "def scale(self, sx: float, sy: float | None = None) -> Element:" in self.c

    def test_element_rotate_multiline(self):
        rotate_lines = [l for l in self.c.splitlines() if "def rotate(" in l]
        assert rotate_lines, "rotate not found"
        assert rotate_lines[0].rstrip().endswith("("), "rotate should be multi-line"

    def test_element_blank_resolves_kwargs(self):
        """blank(**kwargs) -> cls(opacity=0.0, **kwargs): id and title appear; opacity excluded."""
        line = _def_line(_section(self.c, "Element"), "def blank(cls")
        assert "id:" in line
        assert "title:" in line
        assert "opacity" not in line
        assert "**kwargs" not in line

    def test_unused_package_import_not_in_header(self):
        header = self.c.split("\nclass ")[0]
        assert "drawkit" not in header


class TestContainerStub:
    @pytest.fixture(autouse=True)
    def setup(self, container_stub):
        self.c = container_stub

    def test_both_classes_present(self):
        assert "class Container(Element):" in self.c
        assert "class Layer(Container):" in self.c

    def test_element_import_in_header(self):
        header = self.c.split("\nclass ")[0]
        assert _imports_name(header, "drawkit.element", "Element")

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_star_args_preserved(self):
        init = _def_line(_section(self.c, "Container"), "def __init__")
        assert "*elements: Element" in init

    def test_kwargs_resolved_from_element(self):
        init = _def_line(_section(self.c, "Container"), "def __init__")
        assert "id: str | None" in init
        assert "title: str | None" in init
        assert "opacity: float" in init
        assert "**kwargs" not in init

    def test_container_methods(self):
        assert "def add(self, *elements: Element) -> Container:" in self.c
        assert "def remove(self, element: Element) -> Container:" in self.c
        assert "def get(self, index: int) -> Element:" in self.c
        assert "def clone(self, deep: bool = True) -> Container:" in self.c

    def test_container_dunder_methods(self):
        assert "def __iter__(self) -> Iterator[Element]:" in self.c
        assert "def __len__(self) -> int:" in self.c

    def test_layer_three_level_chain(self):
        init = _def_line(_section(self.c, "Layer"), "def __init__")
        for p in ("name: str", "locked: bool", "visible: bool", "label:", "id:", "opacity:"):
            assert p in init, f"Missing: {p}"
        assert "**kwargs" not in init

    def test_layer_visible_not_duplicated(self):
        init = _def_line(_section(self.c, "Layer"), "def __init__")
        assert init.count("visible:") == 1

    def test_layer_kw_only_separator(self):
        init = _def_line(_section(self.c, "Layer"), "def __init__")
        assert "*," in init
        assert init.index("visible:") < init.index("*,") < init.index("label:")

    def test_layer_own_methods(self):
        assert "def lock(self) -> Layer:" in self.c
        assert "def unlock(self) -> Layer:" in self.c
        assert "def hide(self) -> Layer:" in self.c
        assert "def show_layer(self) -> Layer:" in self.c


class TestGraphicsStub:
    @pytest.fixture(autouse=True)
    def setup(self, graphics_stub):
        self.c = graphics_stub

    def test_expected_classes_present(self):
        for cls in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
            assert f"class {cls}" in self.c
        assert "class Element" not in self.c

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_types_import_in_header(self):
        header = self.c.split("\nclass ")[0]
        assert _imports_name(header, "drawkit", "types")

    def test_element_import_in_header(self):
        header = self.c.split("\nclass ")[0]
        assert _imports_name(header, "drawkit.element", "Element")

    def test_arc_fully_resolved(self):
        """Four-level chain: Arc -> Path -> Shape -> Element."""
        arc = _section(self.c, "Arc")
        for p in ("angle: float", "offset: float", "d: str", "clip_path",
                  "fill", "stroke_linecap", "opacity: float"):
            assert p in arc, f"Missing: {p}"
        assert "**kwargs" not in arc

    def test_type_aliases_in_shape(self):
        shape = _section(self.c, "Shape")
        assert "types.Color" in shape
        assert "types.Length" in shape
        assert "types.StrokeLineCap" in shape
        assert "types.StrokeLineJoin" in shape
        assert "str | float | int" not in shape

    def test_optional_aliases_not_expanded(self):
        shape = _section(self.c, "Shape")
        assert "stroke: types.Color | None = None" in shape
        assert "stroke_dasharray: types.DashArray | None = None" in shape
        assert "Tuple[float" not in shape

    def test_type_aliases_propagated_through_kwargs(self):
        for cls_name in ("Path", "Arc", "Rectangle", "Square", "Circle"):
            sec = _section(self.c, cls_name)
            assert "stroke: types.Color | None" in sec, cls_name
            assert "stroke_width: types.Length" in sec, cls_name
            assert "Tuple[float" not in sec, cls_name

    def test_circle_property(self):
        circ = _section(self.c, "Circle")
        assert "@property" in circ
        assert "def area(self) -> float:" in circ

    def test_circle_diameter_property_alias(self):
        assert "def diameter(self) -> types.Length:" in _section(self.c, "Circle")

    def test_circle_unit_classmethod_resolved(self):
        line = _def_line(_section(self.c, "Circle"), "def unit(cls")
        for p in ("fill", "opacity", "stroke_width"):
            assert p in line, f"Missing in unit: {p}"
        param_names = [
            tok.strip().split(":")[0].split("=")[0].strip()
            for tok in line.split("(cls,")[1].split(",")
            if tok.strip()
        ]
        for excluded in ("r", "cx", "cy"):
            assert excluded not in param_names, f"{excluded} should be excluded"
        assert "**kwargs" not in line

    def test_circle_at_origin_keeps_r(self):
        """at_origin has an explicit r param, so r must appear."""
        assert "r:" in _def_line(_section(self.c, "Circle"), "def at_origin(cls")

    def test_rectangle_from_bounds_classmethod(self):
        line = _def_line(_section(self.c, "Rectangle"), "def from_bounds(cls")
        for p in ("x1:", "x2:", "y1:", "y2:", "fill", "opacity"):
            assert p in line
        assert "**kwargs" not in line

    def test_square_inherits_full_chain(self):
        sq = _section(self.c, "Square")
        for p in ("size:", "x:", "y:", "fill", "opacity"):
            assert p in sq, f"Missing in Square: {p}"
        assert "**kwargs" not in sq

    def test_square_drops_params_bound_at_the_super_call(self):
        sq = _section(self.c, "Square")
        assert " width:" not in sq
        assert " height:" not in sq

    def test_path_methods(self):
        assert "def move_to(self, x: float, y: float) -> Path:" in self.c
        assert "def line_to(self, x: float, y: float) -> Path:" in self.c
        assert "def close(self) -> Path:" in self.c
