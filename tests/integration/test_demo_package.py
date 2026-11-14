"""End-to-end stubs for the demo package."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import stubpy
from tests.conftest import assert_valid_syntax, flatten

DEMO_DIR = Path(__file__).parents[2] / "demo"


class TestElementDemo:
    @pytest.fixture(autouse=True)
    def setup(self, element_stub):
        self.c    = element_stub
        self.flat = flatten(element_stub)

    def _sec(self, name: str) -> str:
        return self.c.split(f"class {name}")[1].split("\nclass ")[0]

    def test_both_classes_present(self):
        assert "class Style:"      in self.c
        assert "class Element(ABC):" in self.c

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_style_open_kwargs_preserved(self):
        assert "**props: Any" in self._sec("Style")

    def test_style_classmethod(self):
        s = self._sec("Style")
        assert "@classmethod" in s
        assert "def from_dict(cls, data: Dict[str, Any]) -> Style:" in s

    def test_style_dunder_methods(self):
        s = self._sec("Style")
        assert "def __setitem__" in s
        assert "def __getitem__" in s

    def test_element_init_params(self):
        elem = flatten(self._sec("Element"))
        init = [l for l in elem.splitlines() if "def __init__" in l][0]
        assert ("id: str | None" in init or "id: Optional[str]" in init)
        assert ("title: str | None" in init or "title: Optional[str]" in init)
        assert "opacity: float"       in init
        assert "-> None"              in init

    def test_element_transform_methods(self):
        assert "def translate(self, tx: float, ty: float = 0.0) -> Element:" in self.c
        scale_line_modern = "def scale(self, sx: float, sy: float | None = None) -> Element:"
        scale_line_legacy = "def scale(self, sx: float, sy: Optional[float] = None) -> Element:"
        assert scale_line_modern in self.c or scale_line_legacy in self.c

    def test_element_rotate_multiline(self):
        rotate_lines = [l for l in self.c.splitlines() if "def rotate(" in l]
        assert rotate_lines, "rotate not found"
        assert rotate_lines[0].rstrip().endswith("("), "rotate should be multi-line"

    def test_element_blank_resolves_kwargs(self):
        """blank(**kwargs) → cls(opacity=0.0, **kwargs): id & title appear; opacity excluded."""
        elem    = flatten(self._sec("Element"))
        methods = [l for l in elem.splitlines() if "def blank(cls" in l]
        assert methods, "blank classmethod not found"
        line = methods[0]
        assert "id:"    in line
        assert "title:" in line
        assert "**kwargs" not in line

    def test_no_cross_imports_in_header(self):
        header = self.c.splitlines()[:10]
        non_abc_demo = [l for l in header if l.startswith("from demo") and "abc" not in l]
        assert not non_abc_demo, f"Unexpected demo import in header: {non_abc_demo}"


class TestContainerDemo:
    @pytest.fixture(autouse=True)
    def setup(self, container_stub):
        self.c    = container_stub
        self.flat = flatten(container_stub)

    def _sec(self, name: str) -> str:
        return self.c.split(f"class {name}")[1].split("\nclass ")[0]

    def test_both_classes_present(self):
        assert "class Container(Element):" in self.c
        assert "class Layer(Container):"   in self.c

    def test_element_import_in_header(self):
        header = "\n".join(self.c.splitlines()[:8])
        assert "from demo.element import Element" in header

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_star_args_preserved(self):
        cont = flatten(self._sec("Container"))
        init = [l for l in cont.splitlines() if "def __init__" in l][0]
        assert "*elements: Element" in init

    def test_kwargs_resolved_from_element(self):
        cont = flatten(self._sec("Container"))
        init = [l for l in cont.splitlines() if "def __init__" in l][0]
        assert ("id: str | None" in init or "id: Optional[str]" in init)
        assert ("title: str | None" in init or "title: Optional[str]" in init)
        assert "opacity: float"       in init
        assert "**kwargs"             not in init

    def test_container_methods(self):
        assert "def add(self, *elements: Element) -> Container:" in self.c
        assert "def remove(self, element: Element) -> Container:" in self.c
        assert "def get(self, index: int) -> Element:"           in self.c
        assert "def clone(self, deep: bool = True) -> Container:" in self.c

    def test_container_dunder_methods(self):
        assert "def __iter__(self) -> Iterator[Element]:" in self.c
        assert "def __len__(self) -> int:"                in self.c

    def test_layer_three_level_chain(self):
        layer = flatten(self._sec("Layer"))
        init  = [l for l in layer.splitlines() if "def __init__" in l][0]
        for p in ("name: str", "locked: bool", "visible: bool", "label:", "id:", "opacity:"):
            assert p in init, f"Missing: {p}"
        assert "**kwargs" not in init

    def test_layer_kw_only_separator(self):
        layer = flatten(self._sec("Layer"))
        init  = [l for l in layer.splitlines() if "def __init__" in l][0]
        assert "*," in init
        assert init.index("visible:") < init.index("*,") < init.index("label:")

    def test_layer_own_methods(self):
        assert "def lock(self) -> Layer:"       in self.c
        assert "def unlock(self) -> Layer:"     in self.c
        assert "def hide(self) -> Layer:"       in self.c
        assert "def show_layer(self) -> Layer:" in self.c


class TestGraphicsDemo:
    @pytest.fixture(autouse=True)
    def setup(self, graphics_stub):
        self.c    = graphics_stub
        self.flat = flatten(graphics_stub)

    def _sec(self, name: str) -> str:
        return self.c.split(f"class {name}")[1].split("\nclass ")[0]

    def test_expected_classes_present(self):
        for cls in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
            assert f"class {cls}" in self.c
        assert "class Element:" not in self.c

    def test_valid_syntax(self):
        assert_valid_syntax(self.c)

    def test_types_import_in_header(self):
        header = "\n".join(self.c.splitlines()[:8])
        assert "from demo import types" in header

    def test_element_import_in_header(self):
        header = "\n".join(self.c.splitlines()[:8])
        assert "from demo.element import Element" in header

    def test_arc_fully_resolved(self):
        arc = self._sec("Arc")
        for p in ("angle: float", "offset: float", "d: str", "clip_path",
                  "fill", "stroke_linecap", "opacity: float"):
            assert p in arc, f"Missing: {p}"
        assert "**kwargs" not in arc

    def test_type_aliases_in_shape(self):
        shape = self._sec("Shape")
        assert "types.Color"          in shape
        assert "types.Length"         in shape
        assert "types.StrokeLineCap"  in shape
        assert "types.StrokeLineJoin" in shape
        assert "str | float | int"    not in shape

    def test_type_aliases_propagated_through_kwargs(self):
        rect = self._sec("Rectangle")
        assert "types.Length" in rect
        assert "types.Color"  in rect

    def test_circle_property(self):
        circ = self._sec("Circle")
        assert "@property"               in circ
        assert "def area(self) -> float:" in circ

    def test_circle_diameter_property_alias(self):
        circ = self._sec("Circle")
        assert "def diameter(self) -> types.Length:" in circ

    def test_circle_unit_classmethod_resolved(self):
        circ  = flatten(self._sec("Circle"))
        lines = [l for l in circ.splitlines() if "def unit(cls" in l]
        assert lines, "Circle.unit not found"
        line = lines[0]
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
        """at_origin has explicit r param — it's not hardcoded, so r must appear."""
        circ  = flatten(self._sec("Circle"))
        lines = [l for l in circ.splitlines() if "def at_origin(cls" in l]
        assert lines, "Circle.at_origin not found"
        assert "r:" in lines[0]

    def test_rectangle_from_bounds_classmethod(self):
        rect  = flatten(self._sec("Rectangle"))
        lines = [l for l in rect.splitlines() if "def from_bounds(cls" in l]
        assert lines, "Rectangle.from_bounds not found"
        line = lines[0]
        for p in ("x1:", "x2:", "y1:", "y2:"):
            assert p in line
        assert "fill" in line
        assert "opacity" in line

    def test_square_inherits_full_chain(self):
        sq = self._sec("Square")
        for p in ("size:", "x:", "y:", "fill", "opacity"):
            assert p in sq, f"Missing in Square: {p}"
        assert "**kwargs" not in sq

    def test_square_drops_params_bound_at_the_super_call(self):
        sq = self._sec("Square")
        assert " width:" not in sq
        assert " height:" not in sq

    def test_path_methods(self):
        path = self.c
        assert "def move_to(self, x: float, y: float) -> Path:" in path
        assert "def line_to(self, x: float, y: float) -> Path:" in path
        assert "def close(self) -> Path:"                        in path


@pytest.mark.skipif(not DEMO_DIR.exists(), reason="demo directory not found")


class TestDemoPackage053:
    """Integration tests for the expanded 0.5.3 demo (PixelForge library)."""

    @pytest.fixture(scope="class")
    @classmethod
    def stubs(cls, tmp_path_factory):
        out = str(tmp_path_factory.mktemp("stubs"))
        result = stubpy.generate(str(DEMO_DIR), output=out)
        return {p.name: p.read_text() for p in result.written}, result

    def test_zero_failures(self, stubs):
        _, result = stubs
        assert result.failed == [], f"Failed: {result.failed}"

    def test_all_modules_generated(self, stubs):
        files, _ = stubs
        expected = {
            "primitives.pyi", "scene.pyi", "style.pyi", "export.pyi",
            "functions.pyi", "container.pyi", "element.pyi",
            "graphics.pyi", "mixed.pyi", "types.pyi", "variables.pyi",
        }
        assert expected.issubset(set(files))

    def test_all_stubs_valid_syntax(self, stubs):
        files, _ = stubs
        for name, content in files.items():
            try:
                ast.parse(content)
            except SyntaxError as exc:
                raise AssertionError(f"{name} has invalid syntax: {exc}") from exc

    def test_primitives_typeddict(self, stubs):
        files, _ = stubs
        assert "class RenderOptions(TypedDict, total=False):" in files["primitives.pyi"]

    def test_primitives_enum(self, stubs):
        files, _ = stubs
        content = files["primitives.pyi"]
        assert "class BlendMode(Enum):" in content
        assert "from enum import Enum" in content

    def test_primitives_abc(self, stubs):
        files, _ = stubs
        content = files["primitives.pyi"]
        assert "class Shape(ABC):" in content
        assert "@abstractmethod" in content

    def test_primitives_enum_default(self, stubs):
        """BlendMode.NORMAL must appear as valid Python default."""
        files, _ = stubs
        assert "BlendMode.NORMAL" in files["primitives.pyi"]
        assert "<BlendMode" not in files["primitives.pyi"]

    def test_primitives_kwargs_mro(self, stubs):
        """Circle.__init__ absorbs Shape's kwargs."""
        files, _ = stubs
        content = files["primitives.pyi"]
        assert "blend_mode" in content
        assert "opacity" in content

    def test_style_overloads(self, stubs):
        """style.pyi must have @overload decorators."""
        files, _ = stubs
        assert "@overload" in files["style.pyi"]

    def test_scene_generics(self, stubs):
        """scene.pyi must preserve TypeVar and Generic[T]."""
        files, _ = stubs
        content = files["scene.pyi"]
        assert "TypeVar" in content
        assert "Generic" in content

    def test_export_async(self, stubs):
        """export.pyi must have async def for export_png."""
        files, _ = stubs
        assert "async def export_png" in files["export.pyi"]

    def test_functions_kwargs_expanded(self, stubs):
        """functions.pyi: make_color_red has g, b from make_color."""
        files, _ = stubs
        content = files["functions.pyi"]
        assert "def make_color_red(" in content
        assert "**kwargs" not in content.split("def make_color_red(")[1].split(")")[0]
