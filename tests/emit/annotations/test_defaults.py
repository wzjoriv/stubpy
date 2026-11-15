"""Tests for default_to_str."""
from __future__ import annotations

import enum
import inspect

import pytest

from stubpy.emit.annotations import default_to_str
from tests.conftest import _generate, _parse


class TestDefaultToStr:
    def test_empty_returns_empty_string(self):
        assert default_to_str(inspect.Parameter.empty) == ""

    @pytest.mark.parametrize("value,expected", [
        (None,    "None"),
        ("black", "'black'"),
        (10,      "10"),
        (1.0,     "1.0"),
        (True,    "True"),
        (False,   "False"),
        ([1, 2],  "[1, 2]"),
    ])
    def test_various_defaults(self, value, expected):
        assert default_to_str(value) == expected


class TestDefaultToStrEnums:
    def test_enum_member_renders_as_qualified_name(self):
        class Color(enum.Enum):
            RED = "red"

        result = default_to_str(Color.RED)
        assert result == "Color.RED"

    def test_int_enum_member(self):
        class Level(enum.IntEnum):
            WARNING = 1

        result = default_to_str(Level.WARNING)
        assert result == "Level.WARNING"

    def test_type_as_default(self):
        result = default_to_str(int)
        assert result == "int"

    def test_string_default(self):
        assert default_to_str("hello") == "'hello'"

    def test_none_default(self):
        assert default_to_str(None) == "None"

    def test_float_default(self):
        assert default_to_str(1.5) == "1.5"

    def test_empty_sentinel(self):
        assert default_to_str(inspect.Parameter.empty) == ""

    def test_enum_default_in_generated_stub(self):
        """Enum default must appear as ClassName.MEMBER, not <Enum: val>."""
        stub = _generate(
            """
            import enum
            class Mode(enum.Enum):
                NORMAL = "normal"
            def f(mode: Mode = Mode.NORMAL) -> None: ...
            """,
        )
        assert "Mode.NORMAL" in stub
        assert "<Mode" not in stub
        _parse(stub)
