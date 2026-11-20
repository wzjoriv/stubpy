"""Overloaded constructors, sealed binding classes and return types read from docstrings."""
from __future__ import annotations

import ast
import types

import pytest

from stubpy.compiled.signatures import doc_return_type
from stubpy.config import Config
from stubpy.core._compiled import render_live_module
from stubpy.state.context import StubContext

from .fakes import MODULE, FakeBuiltin

INIT_DOC = (
    "__init__(*args, **kwargs)\nOverloaded function.\n\n"
    "1. __init__(self: fakeext.Shape, side: typing.SupportsFloat) -> None\n\n"
    "A square.\n\n"
    "2. __init__(self: fakeext.Shape, w: typing.SupportsFloat, h: typing.SupportsFloat) -> None\n\n"
    "3. __init__(self: fakeext.Shape, points: collections.abc.Sequence[float]) -> None\n"
)


class pybind11_type(type):
    __module__ = "pybind11_builtins"


class Shape:
    __init__ = FakeBuiltin("__init__", INIT_DOC)
    unit = staticmethod(FakeBuiltin("unit", "Overloaded function.\n\n1. unit() -> fakeext.Shape\n\n2. unit(n: int) -> fakeext.Shape\n"))
    parse = classmethod(FakeBuiltin("parse", "parse(cls: type, text: str) -> fakeext.Shape\n"))
    has = FakeBuiltin("__contains__", "__contains__(self: fakeext.Shape, arg0: int) -> bool\n")
    __next__ = FakeBuiltin("__next__", None)


class Sealed(metaclass=pybind11_type):
    __init__ = object.__init__


class Plain:
    count = FakeBuiltin("count", "count(self)\n\nCount the items.\n\nReturns:\n    int: how many")
    paths = FakeBuiltin("paths", "paths(self)\n\nReturns:\n    list of resulting paths")
    ok = FakeBuiltin("ok", "ok(self)\n\nRuns it and returns True when it worked.")
    shaped = FakeBuiltin("shaped", "shaped(self)\n\n:rtype: list[int]")
    unknown = FakeBuiltin("unknown", "unknown(self)\n\nPositive when open.\n\nReturns:\n    Positive number if open")
    __init__ = FakeBuiltin("__init__", "Plain(size)")


def _stub() -> str:
    module = types.ModuleType(MODULE)
    for cls in (Shape, Sealed, Plain):
        cls.__module__ = MODULE
        setattr(module, cls.__name__, cls)
    text = render_live_module(module, StubContext(config=Config()))
    ast.parse(text)
    return text


@pytest.fixture(scope="module")
def stub() -> str:
    return _stub()


def _block(text: str, header: str) -> str:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace()), len(lines))
    return "\n".join(lines[start:end])


class TestOverloads:
    def test_constructor_overloads(self, stub):
        shape = _block(stub, "class Shape")
        assert shape.count("@overload\n    def __init__") == 3
        assert "*args" not in shape
        assert "def __init__(self, side: SupportsFloat) -> None: ..." in shape

    def test_static_method_overloads(self, stub):
        assert _block(stub, "class Shape").count("@staticmethod") == 2

    def test_class_method(self, stub):
        assert "def parse(cls, text: str) -> Shape: ..." in _block(stub, "class Shape")

    def test_method_registered_under_another_name(self, stub):
        assert "def has(self, arg0: int) -> bool: ..." in _block(stub, "class Shape")

    def test_dunder_without_signature(self, stub):
        assert "def __next__(self): ..." in _block(stub, "class Shape")

    def test_binding_class_without_constructor_has_none(self, stub):
        assert "__init__" not in _block(stub, "class Sealed")


class TestReturnsFromDocstrings:
    def test_section_with_type(self, stub):
        assert "def count(self) -> int: ..." in _block(stub, "class Plain")

    def test_section_with_prose(self, stub):
        assert "def paths(self) -> list: ..." in _block(stub, "class Plain")

    def test_sentence(self, stub):
        assert "def ok(self) -> bool: ..." in _block(stub, "class Plain")

    def test_rtype(self, stub):
        assert "def shaped(self) -> list[int]: ..." in _block(stub, "class Plain")

    def test_unrecognised_prose_stays_untyped(self, stub):
        assert "def unknown(self): ..." in _block(stub, "class Plain")

    @pytest.mark.parametrize("doc, expected", [
        ("x\n\nReturns\n-------\nint\n    the count", "int"),
        ("x\n\nReturns\n-------\nn : float\n    the value", "float"),
        ("x\n\nReturns:\n    bool: whether", "bool"),
        ("Returns a tuple of two.", "tuple"),
        ("Returns a list or None.", None),
        ("Does a thing.", None),
        (None, None),
    ])
    def test_doc_return_type(self, doc, expected):
        assert doc_return_type(doc) == expected
