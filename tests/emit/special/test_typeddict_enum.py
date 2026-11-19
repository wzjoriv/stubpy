"""Tests for TypedDict and Enum stubs."""
from __future__ import annotations

import enum
import importlib.util
import sys
from typing import TypedDict

import pytest

from stubpy.emit import generate_class_stub
from tests.conftest import (
    _ctx,
    _generate,
    _parse,
    make_stub_ctx,
)


class TestTypedDictStub:
    def test_total_true(self):
        class Opts(TypedDict):
            width: int
            height: int

        ctx = _ctx()
        stub = generate_class_stub(Opts, ctx)
        assert "class Opts(TypedDict):" in stub
        assert "width: int" in stub
        assert "height: int" in stub
        assert "total=False" not in stub

    def test_total_false(self):
        class Opts(TypedDict, total=False):
            width: int
            height: int

        ctx = _ctx()
        stub = generate_class_stub(Opts, ctx)
        assert "class Opts(TypedDict, total=False):" in stub

    def test_stub_is_valid_python(self):
        class Config(TypedDict, total=False):
            compact: bool
            indent: str
            dpi: float

        ctx = _ctx()
        stub = generate_class_stub(Config, ctx)
        _parse(stub)

    def test_typeddict_in_generated_file(self):
        stub = _generate(
            """
            from typing import TypedDict
            class RenderOpts(TypedDict, total=False):
                compact: bool
                dpi: float
            """,
        )
        assert "class RenderOpts(TypedDict, total=False):" in stub
        _parse(stub)

    def test_typeddict_import_added(self):
        stub = _generate(
            """
            from typing import TypedDict
            class Opts(TypedDict):
                x: int
            """,
        )
        assert "TypedDict" in stub


class TestEnumStub:
    def test_enum_base_class_rendered(self):
        class Color(enum.Enum):
            RED   = "red"
            GREEN = "green"
            BLUE  = "blue"

        ctx = _ctx()
        stub = generate_class_stub(Color, ctx)
        assert "class Color(Enum):" in stub

    def test_int_enum_base_class(self):
        class Level(enum.IntEnum):
            DEBUG   = 0
            WARNING = 1
            ERROR   = 2

        ctx = _ctx()
        stub = generate_class_stub(Level, ctx)
        assert "class Level(IntEnum):" in stub

    def test_enum_private_methods_suppressed(self):
        class Status(enum.Enum):
            ACTIVE   = "active"
            INACTIVE = "inactive"

        ctx = _ctx()
        stub = generate_class_stub(Status, ctx)
        assert "_generate_next_value_" not in stub
        assert "_missing_" not in stub
        assert "_member_type_" not in stub

    def test_enum_stub_valid_python(self):
        class BlendMode(enum.Enum):
            NORMAL   = "normal"
            MULTIPLY = "multiply"

        ctx = _ctx()
        stub = generate_class_stub(BlendMode, ctx)
        _parse(stub)

    def test_enum_import_added(self):
        stub = _generate(
            """
            import enum
            class Color(enum.Enum):
                RED = "red"
            """,
        )
        assert "from enum import Enum" in stub

    def test_int_enum_import_added(self):
        stub = _generate(
            """
            import enum
            class Level(enum.IntEnum):
                DEBUG = 0
            """,
        )
        assert "IntEnum" in stub


_HOME = "typing" if sys.version_info >= (3, 11) else "typing_extensions"
_NEEDS_HOME = pytest.mark.skipif(
    importlib.util.find_spec(_HOME) is None, reason="typing_extensions is not installed"
)

_QUAL_SRC = f"""
from {_HOME} import NotRequired, Required, TypedDict

class Opts(TypedDict):
    a: int
    b: NotRequired[str]

class Loose(TypedDict, total=False):
    a: int
    b: Required[str]

class Base(TypedDict):
    x: int
    y: NotRequired[int]

class Child(Base, total=False):
    z: str
    w: Required[float]
"""


@_NEEDS_HOME
class TestTypedDictQualifiers:
    def test_total_true_not_required(self):
        stub, _ = make_stub_ctx(_QUAL_SRC)
        assert "class Opts(TypedDict):\n    a: int\n    b: NotRequired[str]" in stub

    def test_total_false_required(self):
        stub, _ = make_stub_ctx(_QUAL_SRC)
        assert "class Loose(TypedDict, total=False):\n    a: int\n    b: Required[str]" in stub

    def test_inheritance_mixing_totality(self):
        stub, _ = make_stub_ctx(_QUAL_SRC)
        child = stub[stub.index("class Child"):]
        assert "class Child(Base, total=False):" in child or "class Child(TypedDict, total=False):" in child
        assert "z: str" in child and "w: Required[float]" in child
        assert "    x: Required[int]\n    y: NotRequired[int]" in child

    def test_typing_extensions_import(self):
        stub, _ = make_stub_ctx(_QUAL_SRC, target_python="3.10")
        assert "from typing_extensions import" in stub
        assert "NotRequired" in stub.split("class ")[0] and "Required" in stub.split("class ")[0]

    def test_typing_import_when_supported(self):
        stub, _ = make_stub_ctx(_QUAL_SRC, target_python="3.12")
        header = stub.split("class ")[0]
        assert "from typing import" in header and "NotRequired" in header
        assert "typing_extensions" not in header

    @pytest.mark.skipif(sys.version_info < (3, 13), reason="ReadOnly needs 3.13")
    def test_read_only(self):
        src = (
            "from typing import ReadOnly, TypedDict\n"
            "class R(TypedDict):\n    a: ReadOnly[int]\n    b: str\n"
        )
        stub, _ = make_stub_ctx(src, target_python="3.13")
        assert "    a: ReadOnly[int]\n    b: str" in stub
        assert "from typing import ReadOnly, TypedDict" in stub


@_NEEDS_HOME
def test_runtime_qualifiers_with_string_annotations():
    src = (
        "from __future__ import annotations\n"
        f"from {_HOME} import NotRequired, TypedDict\n"
        "class S(TypedDict):\n    a: int\n    b: NotRequired[str]\n"
    )
    stub, _ = make_stub_ctx(src)
    assert "    b: NotRequired[str]" in stub
