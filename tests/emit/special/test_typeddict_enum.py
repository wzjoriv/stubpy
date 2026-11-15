"""Tests for TypedDict and Enum stubs."""
from __future__ import annotations

import enum
from typing import TypedDict

from stubpy.emit import generate_class_stub
from tests.conftest import (
    _ctx,
    _generate,
    _parse,
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
