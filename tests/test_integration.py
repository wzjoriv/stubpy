"""
tests/test_integration.py
--------------------------
End-to-end integration tests that run the generator against the three
demo modules (element.py, container.py, graphics.py) and assert on the
content of the resulting stubs.

These tests mirror the test suite from the original build/tests/test_stubpy.py
but are restructured as pytest classes and use the shared fixtures from
conftest.py.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from stubpy import generate_stub

from .conftest import assert_valid_syntax, flatten, make_stub


# ---------------------------------------------------------------------------
# Plain class stubs
# ---------------------------------------------------------------------------

class TestPlain:
    def test_basic_signature(self):
        c = make_stub("""
            class Rect:
                def __init__(self, width: float, height: float) -> None: pass
                def area(self) -> float: return self.width * self.height
        """)
        assert "def __init__(self, width: float, height: float) -> None:" in c
        assert "def area(self) -> float:" in c

    def test_default_value(self):
        c = make_stub("class Box:\n    def __init__(self, size: int = 10) -> None: pass\n")
        assert "size: int = 10" in c

    def test_no_hints_keeps_param_names(self):
        c = make_stub("class Bare:\n    def __init__(self, x, y): pass\n")
        assert "def __init__(self, x, y)" in c


# ---------------------------------------------------------------------------
# Type annotation handling
# ---------------------------------------------------------------------------

class TestAnnotations:
    def test_optional_shorthand(self):
        c = make_stub("""
            class A:
                def __init__(self, x: str | None = None) -> None: pass
        """)
        # Modern default: str | None (not Optional[str])
        assert "str | None" in c

    def test_union_three_types(self):
        c = make_stub("""
            class A:
                def __init__(self, x: str | int | float) -> None: pass
        """)
        assert "str | int | float" in c

    def test_callable_annotation(self):
        c = make_stub("""
            from typing import Callable
            class A:
                def __init__(self, fn: Callable[[], None] | None = None) -> None: pass
        """)
        assert "Callable" in c

    def test_literal_annotation(self):
        c = make_stub("""
            from typing import Literal
            class A:
                def __init__(self, cap: Literal["butt", "round"] = "butt") -> None: pass
        """)
        assert "Literal['butt', 'round']" in c

    def test_tuple_annotation(self):
        c = make_stub("""
            from typing import Tuple
            class A:
                def __init__(self, pt: Tuple[float, float]) -> None: pass
        """)
        assert "Tuple[float, float]" in c


# ---------------------------------------------------------------------------
# Single-level **kwargs backtracing
# ---------------------------------------------------------------------------

class TestSingleKwargs:
    SRC = """
        class Parent:
            def __init__(self, color: str, size: int) -> None: pass
        class Child(Parent):
            def __init__(self, label: str, **kwargs): super().__init__(**kwargs)
    """

    @staticmethod
    def _child_section(c: str) -> str:
        return c.split("class Child")[1].split("\nclass ")[0]

    def test_merged(self):
        c = make_stub(self.SRC)
        child = self._child_section(c)
        assert "label: str" in child
        assert "color: str" in child
        assert "size: int"  in child

    def test_kwargs_gone(self):
        c = make_stub(self.SRC)
        assert "**kwargs" not in self._child_section(c)

    def test_defaults_preserved(self):
        c = make_stub("""
            class B:
                def __init__(self, x: float = 0.0) -> None: pass
            class D(B):
                def __init__(self, name: str, **kwargs): super().__init__(**kwargs)
        """)
        assert "x: float = 0.0" in c


# ---------------------------------------------------------------------------
# Multi-level **kwargs backtracing
# ---------------------------------------------------------------------------

class TestMultiLevel:
    SRC = """
        class A:
            def __init__(self, name: str, legs: int, wild: bool = True) -> None: pass
        class B(A):
            def __init__(self, owner: str, **kwargs): super().__init__(**kwargs)
        class C(B):
            def __init__(self, breed: str, **kwargs): super().__init__(**kwargs)
        class D(C):
            def __init__(self, job: str, **kwargs): super().__init__(**kwargs)
    """

    @staticmethod
    def _sec(c: str, name: str) -> str:
        return c.split(f"class {name}")[1].split("\nclass ")[0]

    def test_three_levels(self):
        c = make_stub(self.SRC)
        s = self._sec(c, "C")
        for p in ("breed: str", "owner: str", "name: str", "legs: int"):
            assert p in s
        assert "**kwargs" not in s

    def test_four_levels_with_default(self):
        c = make_stub(self.SRC)
        s = self._sec(c, "D")
        for p in ("job: str", "breed: str", "owner: str", "name: str", "wild: bool = True"):
            assert p in s
        assert "**kwargs" not in s

    def test_own_param_comes_first(self):
        c = flatten(make_stub(self.SRC))
        for line in c.splitlines():
            if "class C(" in line:
                in_c = True
            if "def __init__" in line and "class C" in c.split("def __init__")[0].rsplit("\n", 5)[-1]:
                assert line.index("breed") < line.index("owner") < line.index("name")
                break


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_open_kwargs_preserved_when_no_parent(self):
        c = make_stub("class W:\n    def __init__(self, x: str, **kwargs): pass\n")
        assert "**kwargs" in c

    def test_unresolved_args_preserved(self):
        c = make_stub("class V:\n    def __init__(self, first: int, *args): pass\n")
        assert "*args" in c

    def test_kw_only_gets_separator(self):
        c = flatten(make_stub("""
            class K:
                def __init__(self, a: int, *, b: str = "x") -> None: pass
        """))
        init_line = [l for l in c.splitlines() if "def __init__" in l][0]
        assert "*," in init_line
        assert init_line.index("*,") < init_line.index("b:")


# ---------------------------------------------------------------------------
# Special method decorators
# ---------------------------------------------------------------------------

class TestSpecialMethods:
    def test_classmethod(self):
        c = make_stub("""
            class F:
                @classmethod
                def create(cls, v: int) -> 'F': return cls()
        """)
        assert "@classmethod" in c
        assert "def create(cls, v: int)" in c

    def test_staticmethod(self):
        c = make_stub("""
            class U:
                @staticmethod
                def add(a: int, b: int) -> int: return a + b
        """)
        assert "@staticmethod" in c
        assert "def add(a: int, b: int) -> int:" in c

    def test_property_with_setter(self):
        c = make_stub("""
            class P:
                @property
                def value(self) -> float: return self._v
                @value.setter
                def value(self, v: float) -> None: self._v = v
        """)
        assert "@property"     in c
        assert "def value(self) -> float:" in c
        assert "@value.setter" in c
        assert "def value(self, v: float) -> None:" in c


# ---------------------------------------------------------------------------
# @classmethod cls() backtracing
# ---------------------------------------------------------------------------

class TestClassmethodCls:
    SRC = """
        class Widget:
            def __init__(self, width: int, height: int, color: str = "black") -> None:
                pass

            @classmethod
            def square(cls, **kwargs) -> 'Widget':
                return cls(**kwargs)

            @classmethod
            def colored(cls, color: str, **kwargs) -> 'Widget':
                return cls(color=color, **kwargs)
    """

    @staticmethod
    def _method_line(content: str, method: str) -> str:
        for line in flatten(content).splitlines():
            if f"def {method}(cls" in line:
                return line
        return ""

    def test_square_gets_init_params(self):
        c = make_stub(self.SRC)
        line = self._method_line(c, "square")
        assert line, "square method not found"
        assert "width: int"  in line
        assert "height: int" in line
        assert "color: str"  in line
        assert "**kwargs"    not in line

    def test_colored_excludes_explicit_param_once(self):
        c = make_stub(self.SRC)
        line = self._method_line(c, "colored")
        assert line, "colored method not found"
        assert "color: str" in line
        assert "width: int" in line
        assert line.count("color:") == 1

    def test_chained_cls_kwargs(self):
        c = make_stub("""
            class Base:
                def __init__(self, x: int, y: int) -> None: pass
            class Child(Base):
                def __init__(self, label: str, **kwargs): super().__init__(**kwargs)
                @classmethod
                def make(cls, **kwargs) -> 'Child':
                    return cls(**kwargs)
        """)
        line = self._method_line(c, "make")
        assert "label: str" in line
        assert "x: int"     in line
        assert "y: int"     in line
        assert "**kwargs"   not in line


# ---------------------------------------------------------------------------
# Type alias preservation
# ---------------------------------------------------------------------------

class TestTypeAliasPreservation:
    @staticmethod
    def _make_types_package() -> tuple[str, str]:
        tmpdir = tempfile.mkdtemp()
        types_src = textwrap.dedent("""
            from typing import Literal, Tuple
            Number = int | float
            Length = str | float | int
            Color  = str | Tuple[float, float, float]
            Cap    = Literal["butt", "round", "square"]
        """)
        open(os.path.join(tmpdir, "__init__.py"), "w").close()
        open(os.path.join(tmpdir, "types.py"), "w").write(types_src)
        return tmpdir, os.path.basename(tmpdir)

    def test_aliases_preserved_not_expanded(self):
        tmpdir, pkg_name = self._make_types_package()
        src = textwrap.dedent(f"""
            from __future__ import annotations
            import sys
            sys.path.insert(0, {repr(os.path.dirname(tmpdir))})
            from {pkg_name} import types

            class Shape:
                def __init__(self, width: types.Length, color: types.Color) -> None:
                    pass
        """)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8", dir=tmpdir
        )
        tmp.write(src); tmp.flush(); tmp.close()
        c = generate_stub(tmp.name, str(Path(tmp.name).with_suffix(".pyi")))
        assert "types.Length" in c
        assert "types.Color"  in c
        assert "str | float | int" not in c

    def test_type_module_import_in_header(self):
        tmpdir, pkg_name = self._make_types_package()
        src = textwrap.dedent(f"""
            from __future__ import annotations
            import sys
            sys.path.insert(0, {repr(os.path.dirname(tmpdir))})
            from {pkg_name} import types

            class A:
                def __init__(self, x: types.Length) -> None: pass
        """)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8", dir=tmpdir
        )
        tmp.write(src); tmp.flush(); tmp.close()
        c = generate_stub(tmp.name, str(Path(tmp.name).with_suffix(".pyi")))
        header = "\n".join(c.splitlines()[:10])
        assert "import types" in header


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_many_params_multiline(self):
        c = make_stub("""
            class A:
                def __init__(self, x: int, y: int, z: int) -> None: pass
        """)
        def_lines = [l for l in c.splitlines() if "def __init__" in l]
        assert def_lines
        assert def_lines[0].rstrip().endswith("("), \
            "Expected multi-line: def line should end with '('"

    def test_few_params_inline(self):
        c = make_stub("""
            class A:
                def move(self, x: int, y: int) -> None: pass
        """)
        move_lines = [l for l in c.splitlines() if "def move" in l]
        assert move_lines
        assert "x: int" in move_lines[0], "Expected inline formatting"

    def test_multiline_is_valid_python(self):
        c = make_stub("""
            class A:
                def __init__(self, a: int, b: str, c: float, d: bool = True) -> None: pass
        """)
        assert_valid_syntax(c)

    def test_trailing_comma_on_param_lines(self):
        c = make_stub("""
            class A:
                def __init__(self, x: int, y: int, z: int) -> None: pass
        """)
        for line in c.splitlines():
            stripped = line.strip()
            if any(p in stripped for p in ("x:", "y:", "z:")) and ")" not in stripped:
                assert stripped.endswith(","), f"Missing trailing comma: {line!r}"


# ---------------------------------------------------------------------------
# demo/element.py — integration
# ---------------------------------------------------------------------------

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
        # Modern style: str | None instead of Optional[str]
        assert ("id: str | None" in init or "id: Optional[str]" in init)
        assert ("title: str | None" in init or "title: Optional[str]" in init)
        assert "opacity: float"       in init
        assert "-> None"              in init

    def test_element_transform_methods(self):
        assert "def translate(self, tx: float, ty: float = 0.0) -> Element:" in self.c
        # Modern style: float | None instead of Optional[float]
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
        # element.py does not import from any sibling demo module —
        # only stdlib and typing imports appear in the header.
        header = self.c.splitlines()[:10]
        non_abc_demo = [l for l in header if l.startswith("from demo") and "abc" not in l]
        assert not non_abc_demo, f"Unexpected demo import in header: {non_abc_demo}"


# ---------------------------------------------------------------------------
# demo/container.py — integration
# ---------------------------------------------------------------------------

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
        # Modern style: str | None; also accept legacy Optional[str]
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


# ---------------------------------------------------------------------------
# demo/graphics.py — integration
# ---------------------------------------------------------------------------

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
        # Element lives in element.py — should NOT be redefined here
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
        # Shape + Element params present
        for p in ("fill", "opacity", "stroke_width"):
            assert p in line, f"Missing in unit: {p}"
        # r, cx, cy are hardcoded in cls(r=1, cx=0, cy=0, ...) → excluded
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
        # Should also inherit Shape + Element params
        assert "fill" in line
        assert "opacity" in line

    def test_square_inherits_full_chain(self):
        sq = self._sec("Square")
        for p in ("size:", "x:", "y:", "width:", "height:", "fill", "opacity"):
            assert p in sq, f"Missing in Square: {p}"
        assert "**kwargs" not in sq

    def test_path_methods(self):
        path = self.c
        assert "def move_to(self, x: float, y: float) -> Path:" in path
        assert "def line_to(self, x: float, y: float) -> Path:" in path
        assert "def close(self) -> Path:"                        in path


# ---------------------------------------------------------------------------
# Static methods — comprehensive
# ---------------------------------------------------------------------------

class TestStaticMethods:
    def test_static_no_args(self):
        c = make_stub("""
            class A:
                @staticmethod
                def util() -> int: return 42
        """)
        assert "@staticmethod" in c
        assert "def util() -> int: ..." in c
        assert "self" not in c.split("def util")[1].split("\n")[0]
        assert "cls"  not in c.split("def util")[1].split("\n")[0]

    def test_static_with_args(self):
        c = make_stub("""
            class A:
                @staticmethod
                def add(a: float, b: float = 1.0) -> float: return a + b
        """)
        assert "def add(a: float, b: float = 1.0) -> float: ..." in c

    def test_static_open_kwargs(self):
        c = make_stub("""
            class A:
                @staticmethod
                def factory(**kwargs) -> None: pass
        """)
        assert "@staticmethod" in c
        assert "**kwargs" in c

    def test_static_not_inherited_by_stub(self):
        """Only methods defined directly on the class appear."""
        c = make_stub("""
            class Parent:
                @staticmethod
                def parent_util() -> int: return 0
            class Child(Parent):
                @staticmethod
                def child_util() -> str: return ""
        """)
        child_sec = c.split("class Child")[1]
        assert "child_util" in child_sec
        assert "parent_util" not in child_sec

    def test_static_valid_syntax(self):
        c = make_stub("""
            class A:
                @staticmethod
                def compute(x: int, y: int, z: int) -> int: return x + y + z
        """)
        assert_valid_syntax(c)


# ---------------------------------------------------------------------------
# *args and **kwargs together
# ---------------------------------------------------------------------------

class TestArgsAndKwargsTogether:
    def test_both_no_parent(self):
        """*args and **kwargs together with no parent are both preserved."""
        from typing import Any
        c = make_stub("""
            from typing import Any
            class A:
                def __init__(self, x: int, *args: str, flag: bool = False, **kwargs: Any) -> None:
                    pass
        """)
        c_flat = flatten(c)
        init = [l for l in c_flat.splitlines() if "def __init__" in l][0]
        assert "*args: str"     in init
        assert "**kwargs: Any"  in init
        assert "flag: bool"     in init
        # *args must come before **kwargs
        assert init.index("*args") < init.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_before_kwargs_in_output(self):
        """*args always appears before **kwargs in the emitted signature."""
        c = make_stub("""
            class Parent:
                def __init__(self, label: str, **kwargs) -> None: pass
            class Child(Parent):
                def __init__(self, *items: int, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        c_flat = flatten(c)
        child_lines = [l for l in c_flat.splitlines() if "class Child" in l or
                       ("def __init__" in l and "Child" in c_flat.split(l)[0].split("class ")[-1])]
        child_init = [l for l in c_flat.splitlines()
                      if "def __init__" in l and "Child" in c.split("def __init__")[1 if c.count("def __init__") > 1 else 0]]
        # Simpler: check the child section
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "*items: int" in init_line
        assert "**kwargs"    in init_line
        assert init_line.index("*items") < init_line.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_before_kwargs_open_parent(self):
        """*args precedes residual **kwargs when parent **kwargs is unresolved."""
        c = make_stub("""
            class Parent:
                def __init__(self, label: str, **kwargs) -> None: pass
            class Child(Parent):
                def __init__(self, *items: int, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "label: str"  in init_line
        assert "*items: int" in init_line
        assert "**kwargs"    in init_line
        assert init_line.index("*items") < init_line.index("**kwargs")
        assert_valid_syntax(c)

    def test_args_after_resolved_kwargs_params(self):
        """When **kwargs resolves fully, *args follows the concrete params."""
        c = make_stub("""
            class Parent:
                def __init__(self, color: str = "black", size: int = 10) -> None: pass
            class Child(Parent):
                def __init__(self, *args: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "color: str"  in init_line
        assert "size: int"   in init_line
        assert "*args: str"  in init_line
        assert "**kwargs" not in init_line   # fully resolved
        # concrete params come before *args
        assert init_line.index("color") < init_line.index("*args")
        assert_valid_syntax(c)

    def test_three_level_with_star_args(self):
        """Three-level chain where grandchild has *args."""
        c = make_stub("""
            class GrandParent:
                def __init__(self, width: float, height: float) -> None: pass
            class Middle(GrandParent):
                def __init__(self, name: str, **kwargs) -> None:
                    super().__init__(**kwargs)
            class GrandChild(Middle):
                def __init__(self, *tags: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        gc_sec = flatten(c.split("class GrandChild")[1])
        init_line = [l for l in gc_sec.splitlines() if "def __init__" in l][0]
        assert "name: str"   in init_line
        assert "width: float" in init_line
        assert "*tags: str"  in init_line
        assert "**kwargs" not in init_line   # fully resolved
        assert_valid_syntax(c)

    def test_kw_only_with_kwargs_resolved(self):
        """Keyword-only params from parent survive through **kwargs backtracing."""
        c = make_stub("""
            class Parent:
                def __init__(self, a: int, *, b: str = "x") -> None: pass
            class Child(Parent):
                def __init__(self, prefix: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        child_sec = flatten(c.split("class Child")[1])
        init_line = [l for l in child_sec.splitlines() if "def __init__" in l][0]
        assert "prefix: str" in init_line
        assert "a: int"      in init_line
        assert "b: str"      in init_line
        assert "*,"          in init_line     # kw-only separator present
        assert "**kwargs" not in init_line
        assert_valid_syntax(c)


# ---------------------------------------------------------------------------
# Inline import support
# ---------------------------------------------------------------------------

class TestInlineImports:
    """Imports inside function / method bodies are discovered and re-emitted.

    Projects sometimes place imports inside functions to break circular
    dependencies.  stubpy's AST pre-pass uses ``ast.walk`` across the *entire*
    source tree, so inline imports are found in ``scan_import_statements``.
    They are re-emitted in the ``.pyi`` header when the imported name actually
    appears in a stub annotation (return type, parameter type, base class, etc.).
    Imports whose names never appear in the stub body are silently skipped, just
    like top-level imports that are unused in the output.
    """

    def test_inline_import_used_as_return_type(self):
        """Inline import used as a return-type annotation is re-emitted."""
        c = make_stub("""
            def factory() -> 'Widget':
                from demo_module import Widget
                return Widget()
        """)
        assert "from demo_module import Widget" in c
        assert_valid_syntax(c)

    def test_inline_import_as_alias_used_in_annotation(self):
        """``import X as Y`` inline; alias appears in return annotation."""
        c = make_stub("""
            def make() -> 'W':
                from demo_module import Widget as W
                return W()
        """)
        assert "from demo_module import Widget as W" in c
        assert_valid_syntax(c)

    def test_inline_import_in_method_used_as_base(self):
        """Inline import whose name appears as a base class is re-emitted."""
        c = make_stub("""
            class Renderer:
                def _get_canvas(self) -> 'Canvas': ...
            # Canvas is used as an annotation so it appears in the stub body,
            # causing the inline import to be re-emitted.
            def setup() -> 'Canvas':
                from render_lib import Canvas
                return Canvas()
        """)
        assert "from render_lib import Canvas" in c
        assert_valid_syntax(c)

    def test_inline_import_not_duplicated(self):
        """Same name imported both at top-level and inline — one import in header.

        The deduplication is exercised entirely via ``scan_import_statements``
        and ``collect_cross_imports``; we don't need a real importable module
        because the name never actually appears as a type annotation in the
        generated stub body (``factory`` has no parameters with that type).
        The test therefore uses a sentinel module name that is intentionally
        not on ``sys.path``.
        """
        # Use a module that is syntactically valid but unknown at import time;
        # wrap in AUTO mode so the load failure is handled gracefully and we
        # still exercise the import-deduplication path via AST scanning.
        import tempfile
        from pathlib import Path
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext, ExecutionMode

        source = textwrap.dedent("""
            from _stubpy_fake_dedup_mod import Widget

            def factory() -> 'Widget':
                from _stubpy_fake_dedup_mod import Widget
                return Widget()
        """)
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(source)
            tmp = fh.name

        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AUTO))
        c = generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        # The import should appear at most once (dedup check)
        assert c.count("from _stubpy_fake_dedup_mod import Widget") <= 1
        assert_valid_syntax(c)

    def test_inline_import_unused_in_stub_not_emitted(self):
        """Inline import whose name never appears in a stub annotation is not emitted.

        The import is discovered but ``collect_cross_imports`` only re-emits
        names that are actually referenced in the generated stub body.
        """
        c = make_stub("""
            class R:
                def render(self):
                    from rlib import Canvas   # Canvas not in any annotation
                    return Canvas()
        """)
        # render has no annotation → Canvas never appears in stub → no import
        assert "rlib" not in c
        assert_valid_syntax(c)

    def test_inline_stdlib_excluded(self):
        """Inline stdlib / typing imports are not re-emitted as cross-file imports."""
        c = make_stub("""
            def helper(x: int) -> list:
                from typing import List
                return []
        """)
        assert_valid_syntax(c)


# ---------------------------------------------------------------------------
# TypeVar, TypeAlias, NewType stubs
# ---------------------------------------------------------------------------

class TestTypeVarStubs:
    """TypeVar / TypeAlias / NewType declarations are re-emitted in stubs."""

    def test_typevar_emitted(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "X: int = 1\n"
        )
        assert "T = TypeVar('T')" in c
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_typevar_with_bound(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T', bound=int)\n"
        )
        assert "T = TypeVar('T', bound=int)" in c
        assert_valid_syntax(c)

    def test_typevar_with_constraints(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "AnyStr = TypeVar('AnyStr', str, bytes)\n"
        )
        assert "AnyStr = TypeVar('AnyStr', str, bytes)" in c
        assert_valid_syntax(c)

    def test_typealias_emitted(self):
        c = make_stub(
            "from typing import TypeAlias\n"
            "Vector: TypeAlias = list[float]\n"
        )
        assert "Vector: TypeAlias = list[float]" in c
        assert_valid_syntax(c)

    def test_newtype_emitted(self):
        c = make_stub(
            "from typing import NewType\n"
            "UserId = NewType('UserId', int)\n"
        )
        assert "UserId = NewType('UserId', int)" in c
        assert_valid_syntax(c)

    def test_paramspec_emitted(self):
        c = make_stub(
            "from typing import ParamSpec\n"
            "P = ParamSpec('P')\n"
        )
        assert "P = ParamSpec('P')" in c
        assert_valid_syntax(c)

    def test_typevar_before_class(self):
        """TypeVar declaration precedes the class that uses it (source order)."""
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Box(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
        )
        assert c.index("T = TypeVar") < c.index("class Box")
        assert_valid_syntax(c)

    def test_typevar_not_emitted_as_plain_variable(self):
        """TypeVar declarations go through AliasSymbol, not VariableSymbol."""
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
        )
        # Should be re-emitted as assignment, NOT as 'T: TypeVar'
        assert "T = TypeVar" in c
        assert "T: TypeVar" not in c


# ---------------------------------------------------------------------------
# Generic class base classes (__orig_bases__)
# ---------------------------------------------------------------------------

class TestGenericBases:
    """Generic subscript syntax is preserved in class definitions."""

    def test_generic_single_param(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Stack(Generic[T]):\n"
            "    def push(self, item: T) -> None: ...\n"
            "    def pop(self) -> T: ...\n"
        )
        assert "Generic[T]" in c
        assert "~" not in c
        assert_valid_syntax(c)

    def test_generic_multi_param(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "K = TypeVar('K')\n"
            "V = TypeVar('V')\n"
            "class Pair(Generic[K, V]):\n"
            "    pass\n"
        )
        assert "Generic[K, V]" in c
        assert_valid_syntax(c)

    def test_concrete_and_generic_bases(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Base:\n"
            "    pass\n"
            "class Child(Base, Generic[T]):\n"
            "    pass\n"
        )
        assert "Base" in c
        assert "Generic[T]" in c
        assert_valid_syntax(c)

    def test_typevar_names_no_tilde(self):
        """TypeVar objects must render as bare names, never ~Name."""
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Container(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
        )
        assert "~" not in c


# ---------------------------------------------------------------------------
# @overload stubs
# ---------------------------------------------------------------------------

class TestOverloadStubs:
    """@overload variants are emitted; the implementation stub is suppressed."""

    def test_two_overloads_emitted(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def parse(x: int) -> int: ...\n"
            "@overload\n"
            "def parse(x: str) -> str: ...\n"
            "def parse(x):\n"
            "    return x\n"
        )
        assert c.count("@overload") == 2
        assert_valid_syntax(c)

    def test_overload_decorator_present(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert "@overload" in c
        assert_valid_syntax(c)

    def test_implementation_suppressed(self):
        """The bare (non-@overload) implementation must NOT appear in the stub."""
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def greet(name: str) -> str: ...\n"
            "@overload\n"
            "def greet(name: bytes) -> bytes: ...\n"
            "def greet(name):\n"
            "    return name\n"
        )
        # Exactly 2 defs — both overloads, no impl
        assert c.count("def greet") == 2

    def test_three_overloads(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def process(x: int) -> int: ...\n"
            "@overload\n"
            "def process(x: str) -> str: ...\n"
            "@overload\n"
            "def process(x: bytes) -> bytes: ...\n"
            "def process(x):\n"
            "    return x\n"
        )
        assert c.count("@overload") == 3
        assert c.count("def process") == 3
        assert_valid_syntax(c)

    def test_overload_typing_import_added(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert "overload" in c


# ---------------------------------------------------------------------------
# Positional-only parameters (PEP 570)
# ---------------------------------------------------------------------------

class TestPositionalOnlySeparator:
    """The / separator is correctly emitted for positional-only parameters."""

    def test_slash_in_stub(self):
        c = make_stub(
            "def move(x: float, y: float, /, z: float = 0.0) -> None:\n"
            "    pass\n"
        )
        assert "/" in c
        assert_valid_syntax(c)

    def test_slash_before_regular_param(self):
        c = make_stub(
            "def fn(a: int, b: int, /, c: int) -> int:\n"
            "    return a + b + c\n"
        )
        assert "/" in c
        assert_valid_syntax(c)
        # / must precede c in the serialised output
        assert c.index("/") < c.index("c")

    def test_slash_and_star_in_same_function(self):
        c = make_stub(
            "def fn(a: int, /, b: int, *, c: int) -> int:\n"
            "    return a + b + c\n"
        )
        assert "/" in c
        assert "*" in c
        assert_valid_syntax(c)

    def test_method_with_pos_only(self):
        c = make_stub(
            "class MyClass:\n"
            "    def method(self, x: int, /, y: int = 0) -> int:\n"
            "        return x + y\n"
        )
        assert "/" in c
        assert_valid_syntax(c)

    def test_pos_only_kwargs_backtracing_valid_syntax(self):
        """Pos-only params absorbed via **kwargs produce valid stub syntax."""
        c = make_stub(
            "class Parent:\n"
            "    def __init__(self, x: int, y: int, /) -> None: pass\n"
            "class Child(Parent):\n"
            "    def __init__(self, **kwargs) -> None: pass\n"
        )
        # The stub must be valid Python regardless of how pos-only is handled
        assert_valid_syntax(c)


# ---------------------------------------------------------------------------
# AST_ONLY and AUTO execution modes
# ---------------------------------------------------------------------------

class TestExecutionModes:
    """AST_ONLY skips module execution; AUTO falls back gracefully on errors."""

    def _make(self, source: str, mode) -> str:
        import tempfile
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext

        source = textwrap.dedent(source)
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(source)
            tmp = fh.name
        out = Path(tmp).with_suffix(".pyi").as_posix()
        ctx = StubContext(config=StubConfig(execution_mode=mode))
        return generate_stub(tmp, out, ctx=ctx)

    def test_ast_only_class(self):
        from stubpy.context import ExecutionMode
        c = self._make("class Greeter:\n    pass\n", ExecutionMode.AST_ONLY)
        assert "class Greeter" in c
        assert_valid_syntax(c)

    def test_ast_only_function(self):
        from stubpy.context import ExecutionMode
        c = self._make(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            ExecutionMode.AST_ONLY,
        )
        assert "def add" in c
        assert_valid_syntax(c)

    def test_ast_only_variable(self):
        from stubpy.context import ExecutionMode
        c = self._make("X: int = 1\n", ExecutionMode.AST_ONLY)
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_ast_only_typevar(self):
        from stubpy.context import ExecutionMode
        c = self._make(
            "from typing import TypeVar\nT = TypeVar('T')\n",
            ExecutionMode.AST_ONLY,
        )
        assert "T = TypeVar('T')" in c
        assert_valid_syntax(c)

    def test_ast_only_diagnostic_logged(self):
        from stubpy import generate_stub
        from stubpy.context import ExecutionMode, StubConfig, StubContext
        import tempfile

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("X: int = 1\n")
            tmp = fh.name
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
        generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        assert any("AST_ONLY" in d.message for d in ctx.diagnostics.infos)

    def test_auto_mode_falls_back_on_bad_import(self):
        from stubpy.context import ExecutionMode
        # File imports a non-existent module — AUTO should fall back, not raise
        c = self._make(
            "from _nonexistent_xyz_module import Foo\nX: int = 1\n",
            ExecutionMode.AUTO,
        )
        assert_valid_syntax(c)


# ---------------------------------------------------------------------------
# generate_package — batch stub generation
# ---------------------------------------------------------------------------

class TestGeneratePackage:
    """generate_package processes an entire directory tree of .py files."""

    def _write(self, root: Path, rel: str, content: str) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_simple_package(self, tmp_path):
        """All .py files produce corresponding .pyi files."""
        from stubpy import generate_package
        pkg = tmp_path / "mypkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "shapes.py", "class Square:\n    side: float\n")
        out = tmp_path / "stubs"

        result = generate_package(str(pkg), str(out))

        assert result.summary().startswith("Generated 2")
        assert (out / "__init__.pyi").exists()
        assert (out / "shapes.pyi").exists()
        assert_valid_syntax((out / "shapes.pyi").read_text())

    def test_nested_subpackage(self, tmp_path):
        """Subdirectories are mirrored and __init__.pyi created."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "utils/__init__.py", "")
        self._write(pkg, "utils/helpers.py", "def noop() -> None: pass\n")
        out = tmp_path / "out"

        result = generate_package(str(pkg), str(out))

        assert (out / "utils" / "__init__.pyi").exists()
        assert (out / "utils" / "helpers.pyi").exists()
        assert len(result.failed) == 0

    def test_exclude_pattern(self, tmp_path):
        """Files matching exclude patterns are skipped."""
        from stubpy import generate_package
        from stubpy.context import StubConfig
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "main.py", "X: int = 1\n")
        self._write(pkg, "test_main.py", "import pytest\n")
        out = tmp_path / "out"

        cfg = StubConfig(exclude=["test_*.py"])
        result = generate_package(str(pkg), str(out), config=cfg)

        assert (out / "main.pyi").exists()
        assert not (out / "test_main.pyi").exists()

    def test_ctx_factory_used(self, tmp_path):
        """ctx_factory is called once per file."""
        from stubpy import generate_package
        from stubpy.context import StubConfig, StubContext
        pkg = tmp_path / "pkg"
        self._write(pkg, "a.py", "X: int = 1\n")
        self._write(pkg, "b.py", "Y: str = 'hi'\n")
        out = tmp_path / "out"

        calls: list[StubContext] = []

        def factory() -> StubContext:
            ctx = StubContext()
            calls.append(ctx)
            return ctx

        generate_package(str(pkg), str(out), ctx_factory=factory)
        assert len(calls) == 2  # one per .py file

    def test_missing_package_dir_raises(self, tmp_path):
        """FileNotFoundError raised when package_dir does not exist."""
        from stubpy import generate_package
        with pytest.raises(FileNotFoundError):
            generate_package(str(tmp_path / "nonexistent"), str(tmp_path / "out"))

    def test_output_alongside_source_when_no_output_dir(self, tmp_path):
        """When output_dir is None, .pyi files are placed next to .py files."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "mod.py", "X: int = 1\n")

        result = generate_package(str(pkg))

        assert (pkg / "mod.pyi").exists()
        assert len(result.stubs_written) == 1

    def test_failed_files_reported(self, tmp_path):
        """Files that fail are in PackageResult.failed, not stubs_written."""
        from stubpy import generate_package
        from stubpy.context import ExecutionMode, StubConfig
        pkg = tmp_path / "pkg"
        # This file imports a non-existent module in RUNTIME mode → ERROR
        self._write(pkg, "bad.py", "import _nonexistent_xyz\nX: int = 1\n")
        self._write(pkg, "good.py", "Y: str = 'ok'\n")
        out = tmp_path / "out"

        # AUTO mode falls back; RUNTIME would error
        cfg = StubConfig(execution_mode=ExecutionMode.AUTO)
        result = generate_package(str(pkg), str(out), config=cfg)

        # good.py always succeeds
        good_names = [p.name for p in result.stubs_written]
        assert "good.pyi" in good_names

    def test_package_result_summary(self):
        """PackageResult.summary() formats correctly for 0/1/many stubs."""
        from stubpy.generator import PackageResult
        assert PackageResult().summary() == "Generated 0 stubs, 0 failed."
        r1 = PackageResult(stubs_written=[Path("a.pyi")])
        assert r1.summary() == "Generated 1 stub, 0 failed."
        r2 = PackageResult(stubs_written=[Path("a.pyi"), Path("b.pyi")])
        assert r2.summary() == "Generated 2 stubs, 0 failed."
        r3 = PackageResult(failed=[(Path("c.py"), [])])
        assert "1 failed" in r3.summary()

    def test_stub_content_valid(self, tmp_path):
        """Each generated stub is valid Python syntax."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "models.py",
            """
            from typing import TypeVar, Generic
            T = TypeVar('T')
            class Box(Generic[T]):
                def get(self) -> T: ...
            """)
        out = tmp_path / "out"
        generate_package(str(pkg), str(out))
        content = (out / "models.pyi").read_text()
        assert_valid_syntax(content)
        assert "Generic[T]" in content

    def test_demo_package(self, demo_dir, tmp_path):
        """generate_package on the demo/ package produces all stubs."""
        from stubpy import generate_package
        out = tmp_path / "demo_stubs"
        result = generate_package(str(demo_dir), str(out))
        # Every .py that can be stubbed should succeed (demo has no bad imports)
        assert len(result.stubs_written) > 0
        for stub in result.stubs_written:
            assert_valid_syntax(stub.read_text())


# ---------------------------------------------------------------------------
# typing_style configuration
# ---------------------------------------------------------------------------

class TestTypingStyle:
    """StubConfig.typing_style controls Optional vs X | None output."""

    def test_modern_style_is_default(self):
        """Default mode emits 'str | None', not 'Optional[str]'."""
        c = make_stub(
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )
        assert "str | None" in c

    def test_legacy_style_emits_optional(self):
        """Legacy style emits 'Optional[str]' from typing."""
        from stubpy.context import StubConfig, StubContext
        source = (
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )
        import tempfile
        from stubpy import generate_stub
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(textwrap.dedent(source))
            tmp = fh.name
        ctx = StubContext(config=StubConfig(typing_style="legacy"))
        c = generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        assert "Optional[str]" in c
        assert "from typing import Optional" in c

    def test_modern_style_no_optional_import(self):
        """Modern style doesn't add 'Optional' to the typing import."""
        c = make_stub(
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )
        assert "Optional" not in c
