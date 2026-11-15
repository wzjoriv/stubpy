"""Tests for stubpy.emit.annotations.defaults.render_default: one renderer for every default."""
from __future__ import annotations

import ast
import enum
import math

import pytest

from stubpy.core.context import StubContext
from stubpy.emit.annotations import render_default
from stubpy.emit.annotations.defaults import NonLiteralDefault, literal_arg


class Mode(enum.Enum):
    FAST = 1


class Bits(enum.Flag):
    A = 1
    B = 2


def _ctx(module_name: str = "somewhere.else", **imports: str) -> StubContext:
    ctx = StubContext()
    ctx.module_name = module_name
    ctx.import_map = dict(imports)
    return ctx


@pytest.mark.parametrize("value, expected", [
    (None, "None"), (True, "True"), (3, "3"), (-2.5, "-2.5"), ("it's \"x\"", repr("it's \"x\"")),
    (b"\x00'\"", repr(b"\x00'\"")), ((), "()"), ((1,), "(1,)"), ([1, "a"], "[1, 'a']"),
    ({"k": [1]}, "{'k': [1]}"), (1 + 2j, "(1+2j)"),
])
def test_literals(value, expected):
    text = render_default(value)
    assert text == expected
    assert ast.literal_eval(text) == value


@pytest.mark.parametrize("value", [
    math.inf, -math.inf, math.nan, complex(math.inf, 0), 10 ** 5000, object(), set(), frozenset({1}),
    "x" * 500, [[[1]]], list(range(50)), len, lambda: 0, NonLiteralDefault("_SENTINEL"),
], ids=lambda v: type(v).__name__)
def test_unrenderable_values_become_ellipsis(value):
    assert render_default(value, _ctx()) == "..."


def test_huge_int_never_converted_to_text():
    assert render_default(10 ** 5000) == "..."
    assert render_default(-(10 ** 5000)) == "..."


def test_enum_member_registers_import():
    ctx = _ctx()
    assert render_default(Mode.FAST, ctx) == "Mode.FAST"
    assert ctx.extra_imports == {"Mode": f"from {__name__} import Mode"}


def test_enum_member_prefers_source_import():
    ctx = _ctx(Mode="from .modes import Mode")
    assert render_default(Mode.FAST, ctx) == "Mode.FAST"
    assert ctx.extra_imports == {"Mode": "from .modes import Mode"}


def test_enum_member_of_current_module_needs_no_import():
    ctx = _ctx(module_name=__name__)
    assert render_default(Mode.FAST, ctx) == "Mode.FAST"
    assert ctx.extra_imports == {}


def test_composite_flag_member_becomes_ellipsis():
    assert render_default(Bits.A | Bits.B, _ctx()) in ("...", "Bits.A|B")
    assert "|" not in render_default(Bits.A | Bits.B, _ctx())


def test_local_enum_from_synthetic_module_becomes_ellipsis():
    local = enum.Enum("Local", "X")
    local.__module__ = "_stubpy_target_x"
    assert render_default(local.X, _ctx()) == "..."


def test_classes_by_name():
    assert render_default(int, _ctx()) == "int"
    assert render_default(Mode, _ctx()) == "Mode"


def test_source_defaults():
    ctx = _ctx(os="import os")
    assert render_default(NonLiteralDefault("os.sep"), ctx) == "os.sep"
    assert render_default(NonLiteralDefault("float('inf')"), ctx) == "..."
    assert render_default(NonLiteralDefault("Config.LIMIT"), ctx) == "..."


def test_literal_arg_has_no_length_limit():
    assert literal_arg("x" * 500) == repr("x" * 500)
    assert literal_arg(object()) is None
