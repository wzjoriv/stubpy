"""Tests for method stubs, including properties."""
from __future__ import annotations

from stubpy.emit import (
    generate_class_stub,
    generate_method_stub,
    methods_defined_on,
)
from stubpy.emit._descriptors import find_property_mro
from stubpy.state.context import StubContext


class TestMethodsDefinedOn:
    def test_returns_own_methods_only(self):
        class Parent:
            def parent_method(self): pass
        class Child(Parent):
            def child_method(self): pass
        names = methods_defined_on(Child)
        assert "child_method"  in names
        assert "parent_method" not in names

    def test_public_dunders_included(self):
        class A:
            def __init__(self): pass
            def __len__(self): return 0
            def __repr__(self): return ""
        names = methods_defined_on(A)
        assert "__init__" in names
        assert "__len__"  in names
        assert "__repr__" in names

    def test_private_dunders_excluded(self):
        class A:
            def __init__(self): pass
            def __weakref__(self): pass
        names = methods_defined_on(A)
        assert "__init__"    in names
        assert "__weakref__" not in names

    def test_classmethod_and_staticmethod_included(self):
        class A:
            @classmethod
            def cls_m(cls): pass
            @staticmethod
            def sta_m(): pass
        names = methods_defined_on(A)
        assert "cls_m" in names
        assert "sta_m" in names

    def test_property_included(self):
        class A:
            @property
            def val(self) -> int: return 0
        names = methods_defined_on(A)
        assert "val" in names


class TestGenerateMethodStubRegular:
    def test_simple_method_inline(self, ctx):
        class A:
            def move(self, x: float, y: float) -> None: pass
        stub = generate_method_stub(A, "move", ctx)
        assert "def move(self, x: float, y: float) -> None: ..." in stub

    def test_no_return_annotation(self, ctx):
        class A:
            def run(self): pass
        stub = generate_method_stub(A, "run", ctx)
        assert "def run(self)" in stub
        assert "->" not in stub

    def test_init_always_returns_none(self, ctx):
        class A:
            def __init__(self, x: int): pass
        stub = generate_method_stub(A, "__init__", ctx)
        assert "-> None" in stub

    def test_multiline_for_many_params(self, ctx):
        class A:
            def foo(self, a: int, b: str, c: float) -> None: pass
        stub = generate_method_stub(A, "foo", ctx)
        first_line = stub.splitlines()[0]
        assert first_line.rstrip().endswith("(")

    def test_trailing_comma_in_multiline(self, ctx):
        class A:
            def foo(self, a: int, b: str, c: float) -> None: pass
        stub = generate_method_stub(A, "foo", ctx)
        param_lines = [
            l for l in stub.splitlines()
            if l.strip() and not l.strip().startswith("def ")
            and not l.strip().startswith(")")
        ]
        for line in param_lines:
            assert line.rstrip().endswith(","), f"No trailing comma: {line!r}"

    def test_method_not_on_class_returns_empty(self, ctx):
        class A:
            pass
        stub = generate_method_stub(A, "nonexistent", ctx)
        assert stub == ""


class TestGenerateMethodStubProperty:
    def test_property_decorator_emitted(self, ctx):
        class A:
            @property
            def value(self) -> float: return 0.0
        stub = generate_method_stub(A, "value", ctx)
        assert "@property" in stub
        assert "def value(self) -> float: ..." in stub

    def test_property_with_setter(self, ctx):
        class A:
            @property
            def value(self) -> float: return self._v
            @value.setter
            def value(self, v: float) -> None: self._v = v
        stub = generate_method_stub(A, "value", ctx)
        assert "@property"      in stub
        assert "@value.setter"  in stub
        assert "def value(self, v: float) -> None: ..." in stub

    def test_property_no_return_annotation(self, ctx):
        class A:
            @property
            def name(self): return ""
        stub = generate_method_stub(A, "name", ctx)
        assert "@property" in stub
        assert "def name(self)" in stub

    def test_property_without_setter_no_setter_in_stub(self, ctx):
        class A:
            @property
            def val(self) -> int: return 0
        stub = generate_method_stub(A, "val", ctx)
        assert "@val.setter" not in stub


class TestGenerateMethodStubDecorated:
    def test_classmethod_decorator(self, ctx):
        class A:
            @classmethod
            def create(cls, v: int) -> "A": return cls()
        stub = generate_method_stub(A, "create", ctx)
        assert "@classmethod" in stub
        assert "def create(cls, v: int)" in stub

    def test_staticmethod_decorator(self, ctx):
        class A:
            @staticmethod
            def add(a: int, b: int) -> int: return a + b
        stub = generate_method_stub(A, "add", ctx)
        assert "@staticmethod" in stub
        assert "def add(a: int, b: int) -> int: ..." in stub

    def test_classmethod_no_self_in_sig(self, ctx):
        class A:
            @classmethod
            def make(cls) -> "A": return cls()
        stub = generate_method_stub(A, "make", ctx)
        assert "self" not in stub
        assert "cls"  in stub

    def test_staticmethod_no_self_or_cls(self, ctx):
        class A:
            @staticmethod
            def util(x: int) -> int: return x
        stub = generate_method_stub(A, "util", ctx)
        assert "self" not in stub
        assert "cls"  not in stub


class TestFindPropertyMro:
    """Unit tests for the find_property_mro helper."""

    def test_simple_property_on_class(self):
        class A:
            @property
            def x(self) -> int:
                return 0

        prop = find_property_mro(A, "x")
        assert prop is not None
        assert prop.fget is not None

    def test_getter_and_setter_on_same_class(self):
        class A:
            @property
            def x(self) -> int:
                return 0

            @x.setter
            def x(self, v: int) -> None:
                pass

        prop = find_property_mro(A, "x")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None

    def test_child_only_getter_finds_parent_setter(self):
        """Child overrides getter only — MRO should find parent setter."""
        class Parent:
            @property
            def color(self) -> str:
                return "red"

            @color.setter
            def color(self, v: str) -> None:
                pass

        class Child(Parent):
            @property
            def color(self) -> str:
                return "blue"

        prop = find_property_mro(Child, "color")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None

    def test_child_only_setter_finds_parent_getter(self):
        """Child overrides setter only — MRO should find parent getter."""
        class Parent:
            @property
            def value(self) -> float:
                return 0.0

            @value.setter
            def value(self, v: float) -> None:
                pass

        class Child(Parent):
            value = property(Parent.value.fget, lambda self, v: None)

        prop = find_property_mro(Child, "value")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None

    def test_not_a_property_returns_none(self):
        class A:
            def x(self) -> int:
                return 0

        assert find_property_mro(A, "x") is None

    def test_missing_attribute_returns_none(self):
        class A:
            pass

        assert find_property_mro(A, "nonexistent") is None

    def test_deep_mro_chain(self):
        """Property scattered across 3 levels of inheritance."""
        class GrandParent:
            @property
            def p(self) -> str:
                return ""

        class Parent(GrandParent):
            p = property(GrandParent.p.fget, lambda self, v: None)

        class Child(Parent):
            p = property(Parent.p.fget, lambda self, v: None)

        prop = find_property_mro(Child, "p")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None


class TestPropertyMROInStubs:
    """Integration: generate_method_stub uses MRO-complete property."""

    def test_child_getter_only_emits_inherited_setter(self):
        class Parent:
            @property
            def color(self) -> str:
                return ""

            @color.setter
            def color(self, v: str) -> None:
                pass

        class Child(Parent):
            @property
            def color(self) -> str:
                return "blue"

        ctx = StubContext()
        stub = generate_method_stub(Child, "color", ctx)
        assert "@property" in stub
        assert "@color.setter" in stub
        assert "-> str" in stub

    def test_full_class_stub_includes_setter(self):
        class ColorMixin:
            @property
            def color(self) -> str:
                return ""

            @color.setter
            def color(self, v: str) -> None:
                pass

        class ColoredWidget(ColorMixin):
            @property
            def color(self) -> str:
                return "blue"

        ctx = StubContext()
        stub = generate_class_stub(ColoredWidget, ctx)
        assert "@property" in stub
        assert "@color.setter" in stub

    def test_no_setter_in_entire_mro_omits_setter(self):
        class A:
            @property
            def x(self) -> int:
                return 0

        class B(A):
            @property
            def x(self) -> int:
                return 1

        ctx = StubContext()
        stub = generate_method_stub(B, "x", ctx)
        assert "@property" in stub
        assert "@x.setter" not in stub

    def test_property_return_type_from_parent_getter(self):
        """When child getter has no annotation, parent's type should propagate."""
        class Parent:
            @property
            def size(self) -> float:
                return 0.0

        class Child(Parent):
            @property
            def size(self) -> float:
                return 1.0

        ctx = StubContext()
        stub = generate_method_stub(Child, "size", ctx)
        assert "-> float" in stub
