"""Symbol tables and stubs built from fake compiled modules."""
from __future__ import annotations

import ast
import types

import pytest

from stubpy.analysis.symbols import ClassSymbol, FunctionSymbol, OverloadGroup, VariableSymbol
from stubpy.compiled.introspect import build_compiled_table
from stubpy.config import Config
from stubpy.core._compiled import render_live_module
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Level

from .fakes import Widget, fake_module


def _render(module: types.ModuleType | None = None, **config: object) -> tuple[str, StubContext]:
    ctx = StubContext(config=Config(**config))
    text = render_live_module(module or fake_module(), ctx)
    ast.parse(text)
    return text, ctx


@pytest.fixture(scope="module")
def stub() -> str:
    return _render()[0]


def _block(text: str, header: str) -> str:
    """The lines of the class or def that starts with *header*, up to the next top-level statement."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace()
                and not lines[i].startswith(")")), len(lines))
    return "\n".join(lines[start:end])


class TestTable:
    def test_symbol_kinds(self):
        table = build_compiled_table(fake_module()).table
        assert isinstance(table.get("Widget"), ClassSymbol)
        assert isinstance(table.get("area"), FunctionSymbol)
        assert isinstance(table.get("blur"), OverloadGroup)
        assert isinstance(table.get("COUNT"), VariableSymbol)

    def test_symbols_have_no_live_objects(self):
        table = build_compiled_table(fake_module()).table
        assert table.get("Widget").live_type is None
        assert table.get("area").live_func is None

    def test_modules_and_imported_callables_are_skipped(self):
        table = build_compiled_table(fake_module()).table
        assert "np" not in table and "imported" not in table

    def test_private_names_are_hidden(self):
        table = build_compiled_table(fake_module()).table
        assert "_private" not in table and "_private" in table.hidden_names()
        assert "_private" in build_compiled_table(fake_module(), include_private=True).table

    def test_all_is_respected(self):
        built = build_compiled_table(fake_module(__all__=["area"]))
        assert built.all_names == ["area"]
        assert built.table.all_names() == ["area"]

    def test_imports_are_collected(self):
        imports = build_compiled_table(fake_module()).imports
        assert imports["numpy"] == "import numpy"
        assert imports["SupportsFloat"] == "from typing import SupportsFloat"


class TestFunctions:
    def test_text_signature_keeps_positional_only(self, stub):
        assert "def area(points, /): ..." in stub

    def test_pybind_overloads(self, stub):
        assert stub.count("def blur(") == 2
        assert "@overload\ndef blur(" in stub
        assert "std: SupportsFloat" in stub and "numpy.typing.NDArray[numpy.float32]" in stub

    def test_nanobind_signature_keyword_only_and_default(self, stub):
        block = _block(stub, "def over(")
        assert "*," in block and "opacity: float = 1.0" in block
        assert "dst: numpy.typing.NDArray[numpy.float32]" in block

    def test_cython_c_types(self, stub):
        assert "a: float" in _block(stub, "def lerp(") and "-> float" in _block(stub, "def lerp(")
        fill = _block(stub, "def fill(")
        assert "out: Buffer" in fill and "value: int" in fill and "-> None" in fill
        assert "from typing_extensions import Buffer" in stub

    def test_unknown_signature_is_generic_with_info(self):
        text, ctx = _render()
        assert "def opaque(*args: Any, **kwargs: Any) -> Any: ..." in text
        assert any(d.level is Level.INFO and d.symbol == "opaque" for d in ctx.diagnostics)

    def test_hint_signature_wins(self, stub):
        assert "def hinted(x: float) -> float: ..." in stub

    def test_docstrings_without_signature_lines(self):
        text, _ = _render(include_docstrings=True)
        assert '"""Shoelace area."""' in text
        assert '"""Interpolate."""' in text
        assert "lerp(double" not in text


class TestClasses:
    def test_constructor_overloads(self, stub):
        widget = _block(stub, "class Widget")
        assert widget.count("def __init__(") == 2
        assert "def __init__(self) -> None: ..." in widget
        assert "size: SupportsInt" in widget and "mode: Mode = Mode.FAST" in widget

    def test_methods_drop_the_typed_receiver(self, stub):
        assert "def resize(self, w: int, h: int) -> Widget: ..." in stub

    def test_static_method(self, stub):
        assert "@staticmethod\n    def make(n: int = 3) -> Widget: ..." in stub

    def test_read_only_and_writable_properties(self, stub):
        widget = _block(stub, "class Widget")
        assert "def width(self) -> int: ..." in widget
        assert "@width.setter" not in widget
        assert "@height.setter" in widget and "def height(self, value: SupportsFloat) -> None" in widget

    def test_member_descriptor_is_writable(self, stub):
        assert "@tag.setter" in _block(stub, "class Widget")

    def test_class_constant(self, stub):
        assert "LIMIT: ClassVar[int]" in stub

    def test_nested_class(self, stub):
        widget = _block(stub, "class Widget")
        assert "    class Kind:" in widget and "        def clear(self) -> None: ..." in widget

    def test_method_without_signature(self, stub):
        assert "def mystery(self, *args: Any, **kwargs: Any) -> Any: ..." in stub

    def test_class_docstring(self):
        text, _ = _render(include_docstrings=True)
        assert 'class Widget:\n    """A widget."""' in text
        assert '"""Width in pixels."""' in text


class TestEnums:
    def test_pybind_enum_members_and_accessors(self, stub):
        mode = _block(stub, "class Mode")
        assert "FAST: ClassVar[Mode]" in mode and "SLOW: ClassVar[Mode]" in mode
        assert "def __init__(self, value: SupportsInt) -> None: ..." in mode
        assert "def name(self) -> str: ..." in mode and "def value(self) -> int: ..." in mode

    def test_real_enum(self, stub):
        assert "class Cap(Enum):\n    BUTT = 0\n    ROUND = 1" in stub
        assert "from enum import Enum" in stub

    def test_exported_member_is_typed_by_its_class(self, stub):
        assert "FAST: Mode" in stub


class TestValues:
    def test_constants(self, stub):
        assert "COUNT: int" in stub
        assert "NAMES: tuple[str, ...]" in stub


def test_probe_finds_read_only_getset():
    from stubpy.compiled.introspect._values import is_writable

    descriptor = int.__dict__.get("real")
    if not isinstance(descriptor, types.GetSetDescriptorType):
        pytest.skip("int.real is not a getset descriptor on this interpreter")
    assert is_writable(int, descriptor) is False
    assert is_writable(Widget, Widget.__dict__["tag"]) is True


class TestEnumDefaults:
    def test_member_of_local_enum(self, stub):
        assert "mode: Mode = Mode.FAST" in _block(stub, "class Widget")

    def test_enum_of_another_module_is_qualified_and_imported(self):
        from .fakes import FakeBuiltin

        pick = FakeBuiltin("pick", "pick(c: other.Color = <Color.RED: 0>) -> None\n")
        text, _ = _render(fake_module(pick=pick))
        assert "def pick(c: other.Color = other.Color.RED) -> None: ..." in text and "import other\n" in text
