"""Tests for dataclass stubs."""
from __future__ import annotations

import dataclasses as _dc
import typing

from stubpy.core.context import StubContext
from stubpy.emit import generate_class_stub
from stubpy.emit.special.detect import is_dataclass, is_namedtuple
from tests.conftest import (
    assert_valid_syntax,
    flatten,
    make_stub,
)


class TestDataclassDetection:

    def test_decorated_is_dataclass(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert is_dataclass(Foo)

    def test_plain_class_not_dataclass(self):
        class Plain:
            x: int = 0
        assert not is_dataclass(Plain)

    def test_dataclass_not_namedtuple(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert not is_namedtuple(Foo)


class TestDataclassStubUnit:

    def test_decorator_emitted(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert stub.splitlines()[0] == "@dataclass"
        assert "class Point:" in stub.splitlines()[1]

    def test_init_synthesised(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float = 0.0
        stub = generate_class_stub(Point, StubContext())
        assert "def __init__" in stub
        assert "x: float" in stub
        assert "y: float = 0.0" in stub

    def test_default_factory(self):
        @_dc.dataclass
        class Bag:
            items: list = _dc.field(default_factory=list)
        stub = flatten(generate_class_stub(Bag, StubContext()))
        assert "items: list = ..." in stub

    def test_init_false_excluded_from_init(self):
        @_dc.dataclass
        class Config:
            name: str
            _computed: int = _dc.field(default=0, init=False)
        stub = flatten(generate_class_stub(Config, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "_computed" not in init_line

    def test_classvar_excluded_from_init(self):
        @_dc.dataclass
        class Model:
            MAX: typing.ClassVar[int] = 100
            value: int = 0
        stub = flatten(generate_class_stub(Model, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_annotations_in_body(self):
        @_dc.dataclass
        class Product:
            name: str
            price: float = 9.99
        stub = generate_class_stub(Product, StubContext())
        assert "name: str" in stub
        assert "price: float" in stub

    def test_post_init_included(self):
        @_dc.dataclass
        class Validated:
            x: int
            def __post_init__(self) -> None:
                assert self.x >= 0
        stub = generate_class_stub(Validated, StubContext())
        assert "__post_init__" in stub

    def test_inherited_fields_annotated(self):
        @_dc.dataclass
        class Base:
            x: int
        @_dc.dataclass
        class Child(Base):
            y: str
        stub = flatten(generate_class_stub(Child, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line


class TestDataclassIntegration:

    def test_basic_dataclass(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "def __init__" in c

    def test_dataclasses_import_in_header(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Foo:\n"
            "    x: int\n"
        )
        assert "from dataclasses import dataclass" in c

    def test_default_factory_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Bag:\n"
            "    items: list = field(default_factory=list)\n"
        )
        assert_valid_syntax(c)
        assert "items: list = ..." in flatten(c)

    def test_init_false_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Config:\n"
            "    name: str\n"
            "    counter: int = field(default=0, init=False)\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "counter" not in init_line

    def test_classvar_not_in_init_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "from typing import ClassVar\n"
            "@dataclass\n"
            "class Model:\n"
            "    MAX: ClassVar[int] = 100\n"
            "    value: int = 0\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_dataclass_inheritance_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Base:\n"
            "    x: int\n"
            "@dataclass\n"
            "class Child(Base):\n"
            "    y: str\n"
        )
        assert_valid_syntax(c)
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line

    def test_complex_dataclass_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from dataclasses import dataclass, field\n"
            "from typing import ClassVar, Optional\n"
            "@dataclass\n"
            "class Record:\n"
            "    MAX: ClassVar[int] = 1000\n"
            "    id: int\n"
            "    name: str = 'unnamed'\n"
            "    tags: list = field(default_factory=list)\n"
            "    _internal: bool = field(default=False, init=False)\n"
            "    def validate(self) -> bool: return True\n"
        ))
