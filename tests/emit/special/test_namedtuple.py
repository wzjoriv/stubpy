"""Tests for NamedTuple stubs."""
from __future__ import annotations

import typing
from typing import NamedTuple

from stubpy.core.context import StubContext
from stubpy.emit import generate_class_stub
from stubpy.emit.special.detect import is_namedtuple
from tests.conftest import (
    _ctx,
    _parse,
    assert_valid_syntax,
    make_stub,
)


class TestNamedTupleDetection:

    def test_typed_namedtuple(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        assert is_namedtuple(Point)

    def test_plain_class_not_namedtuple(self):
        class Foo:
            x: int
        assert not is_namedtuple(Foo)

    def test_plain_tuple_subclass_not_namedtuple(self):
        class T(tuple):
            pass
        assert not is_namedtuple(T)


class TestNamedTupleStubUnit:

    def test_class_line(self):
        class Color(typing.NamedTuple):
            r: int
            g: int
        assert generate_class_stub(Color, StubContext()).startswith("class Color(NamedTuple):")

    def test_field_annotations(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert "x: float" in stub
        assert "y: float" in stub

    def test_default_values(self):
        class Color(typing.NamedTuple):
            r: int
            g: int = 0
            b: int = 0
        stub = generate_class_stub(Color, StubContext())
        assert "r: int" in stub
        assert "g: int = 0" in stub
        assert "b: int = 0" in stub

    def test_no_generated_methods(self):
        class Pair(typing.NamedTuple):
            a: str
            b: str
        stub = generate_class_stub(Pair, StubContext())
        assert "_make" not in stub
        assert "_asdict" not in stub
        assert "_replace" not in stub

    def test_uses_namedtuple_base_not_tuple(self):
        class Point(typing.NamedTuple):
            x: float
        stub = generate_class_stub(Point, StubContext())
        assert "class Point(NamedTuple):" in stub
        assert "class Point(tuple):" not in stub

    def test_empty_namedtuple(self):
        class Empty(typing.NamedTuple):
            pass
        stub = generate_class_stub(Empty, StubContext())
        assert "class Empty(NamedTuple):" in stub
        assert "..." in stub


class TestNamedTupleIntegration:

    def test_namedtuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "r: int" in c
        assert "g: int = 0" in c

    def test_namedtuple_import_in_header(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
        )
        assert "from typing import NamedTuple" in c

    def test_multiple_namedtuples(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
            "class RGB(NamedTuple):\n"
            "    r: int\n"
            "    g: int\n"
            "    b: int\n"
        )
        assert_valid_syntax(c)
        assert "class Point(NamedTuple):" in c
        assert "class RGB(NamedTuple):" in c

    def test_no_tuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
        )
        assert "class Point(NamedTuple):" in c
        assert "tuple" not in c

    def test_namedtuple_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from typing import NamedTuple\n"
            "class Vector(NamedTuple):\n"
            "    x: float = 0.0\n"
            "    y: float = 0.0\n"
            "    z: float = 0.0\n"
        ))

    def test_namedtuple_and_class_coexist(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Size(NamedTuple):\n"
            "    width: int\n"
            "    height: int\n"
            "class Canvas:\n"
            "    def __init__(self, size: 'Size') -> None: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Size(NamedTuple):" in c
        assert "class Canvas:" in c


class TestNamedTupleWithMethods:
    def test_property_emitted(self):
        class Point(NamedTuple):
            x: float
            y: float

            @property
            def magnitude(self) -> float:
                return (self.x**2 + self.y**2) ** 0.5

        ctx = _ctx()
        stub = generate_class_stub(Point, ctx)
        assert "@property" in stub
        assert "def magnitude" in stub

    def test_custom_method_emitted(self):
        class Vector(NamedTuple):
            x: float
            y: float

            def dot(self, other: "Vector") -> float:
                return self.x * other.x + self.y * other.y

        ctx = _ctx()
        stub = generate_class_stub(Vector, ctx)
        assert "def dot" in stub

    def test_nt_internals_suppressed(self):
        class Color(NamedTuple):
            r: float
            g: float
            b: float

        ctx = _ctx()
        stub = generate_class_stub(Color, ctx)
        assert "_make" not in stub
        assert "_asdict" not in stub
        assert "_replace" not in stub

    def test_stub_with_methods_valid_python(self):
        class BBox(NamedTuple):
            x: float
            y: float
            w: float
            h: float

            @property
            def right(self) -> float:
                return self.x + self.w

            def area(self) -> float:
                return self.w * self.h

        ctx = _ctx()
        stub = generate_class_stub(BBox, ctx)
        _parse(stub)
