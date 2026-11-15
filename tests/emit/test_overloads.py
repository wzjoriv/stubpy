"""Tests for @overload stubs."""
from __future__ import annotations

import ast

from stubpy.analysis.harvest import FunctionInfo
from stubpy.analysis.symbols import (
    FunctionSymbol,
    OverloadGroup,
)
from stubpy.emit import generate_overload_group_stub
from tests.conftest import (
    assert_valid_syntax,
    make_stub,
)


class TestOverloadGroupStub:
    """generate_overload_group_stub emits @overload for each variant."""

    def test_two_variants_two_overloads(self, ctx):
        fi1 = FunctionInfo("f", 1, raw_return_annotation="int",
                           raw_arg_annotations={"x": "int"})
        fi2 = FunctionInfo("f", 3, raw_return_annotation="str",
                           raw_arg_annotations={"x": "str"})
        sym1 = FunctionSymbol("f", 1, ast_info=fi1)
        sym2 = FunctionSymbol("f", 3, ast_info=fi2)
        group = OverloadGroup("f", 1, variants=[sym1, sym2])
        stub = generate_overload_group_stub(group, ctx)
        assert stub.count("@overload") == 2

    def test_empty_group_returns_empty(self, ctx):
        group = OverloadGroup("f", 1, variants=[])
        assert generate_overload_group_stub(group, ctx) == ""

    def test_stub_is_valid_syntax(self, ctx):
        fi1 = FunctionInfo("f", 1, raw_return_annotation="int",
                           raw_arg_annotations={"x": "int"})
        fi2 = FunctionInfo("f", 3, raw_return_annotation="str",
                           raw_arg_annotations={"x": "str"})
        sym1 = FunctionSymbol("f", 1, ast_info=fi1)
        sym2 = FunctionSymbol("f", 3, ast_info=fi2)
        group = OverloadGroup("f", 1, variants=[sym1, sym2])
        stub = generate_overload_group_stub(group, ctx)
        ast.parse(stub + "\ndef f(*a): ...")


class TestOverloadStubGeneration:
    """Module-level @overload stubs are generated and implementation is suppressed."""

    def test_overload_count(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert c.count("@overload") == 2

    def test_implementation_not_emitted(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert c.count("def f") == 2

    def test_overload_valid_syntax(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def convert(x: int) -> str: ...\n"
            "@overload\n"
            "def convert(x: str) -> int: ...\n"
            "def convert(x): return x\n"
        )
        assert_valid_syntax(c)
