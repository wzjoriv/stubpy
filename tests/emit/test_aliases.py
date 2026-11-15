"""Tests for TypeVar / TypeAlias / NewType stubs."""
from __future__ import annotations

from stubpy.analysis.symbols import AliasSymbol
from stubpy.config import StubConfig
from stubpy.core.context import StubContext
from stubpy.emit import generate_alias_stub
from tests.conftest import (
    assert_valid_syntax,
    make_stub,
)


class TestAliasStub:
    """generate_alias_stub emits TypeVar / TypeAlias / NewType declarations."""

    def test_typevar_simple(self, ctx):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "T = TypeVar('T')"

    def test_typevar_with_bound(self, ctx):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T', bound=int)")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "T = TypeVar('T', bound=int)"

    def test_typealias(self, ctx):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="Vector", lineno=1, kind="TypeAlias", source_str="list[float]")
        sym = AliasSymbol("Vector", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "Vector: TypeAlias = list[float]"

    def test_newtype(self, ctx):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="UserId", lineno=1, kind="NewType", source_str="NewType('UserId', int)")
        sym = AliasSymbol("UserId", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "UserId = NewType('UserId', int)"

    def test_no_ast_info_returns_empty(self, ctx):
        sym = AliasSymbol("T", lineno=1, ast_info=None)
        assert generate_alias_stub(sym, ctx) == ""

    def test_paramspec(self, ctx):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="P", lineno=1, kind="ParamSpec", source_str="ParamSpec('P')")
        sym = AliasSymbol("P", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "P = ParamSpec('P')"


class TestTypeAliasStyle:
    """generate_alias_stub respects alias_style configuration."""

    def _alias_sym(self, name: str, rhs: str):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name=name, lineno=1, kind="TypeAlias", source_str=rhs)
        return AliasSymbol(name, lineno=1, ast_info=tv)

    def test_compatible_emits_typealias(self):
        ctx = StubContext(config=StubConfig(alias_style="compatible"))
        sym = self._alias_sym("Color", "str | tuple[float, ...]")
        result = generate_alias_stub(sym, ctx)
        assert result == "Color: TypeAlias = str | tuple[float, ...]"

    def test_pep695_emits_type_keyword(self):
        ctx = StubContext(config=StubConfig(alias_style="pep695"))
        sym = self._alias_sym("Vector", "list[float]")
        result = generate_alias_stub(sym, ctx)
        assert result == "type Vector = list[float]"

    def test_auto_on_3_12_uses_pep695(self):
        import sys

        ctx = StubContext(config=StubConfig(alias_style="auto"))
        sym = self._alias_sym("Number", "int | float")
        result = generate_alias_stub(sym, ctx)
        if sys.version_info >= (3, 12):
            assert result.startswith("type ")
        else:
            assert ": TypeAlias" in result

    def test_default_is_compatible(self):
        ctx = StubContext()
        sym = self._alias_sym("Length", "str | float | int")
        result = generate_alias_stub(sym, ctx)
        assert ": TypeAlias" in result

    def test_typevar_unaffected_by_style(self):
        from stubpy.analysis.harvest import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        for style in ("compatible", "pep695", "auto"):
            ctx = StubContext(config=StubConfig(alias_style=style))
            result = generate_alias_stub(sym, ctx)
            assert result == "T = TypeVar('T')"


class TestAliasStubGeneration:
    """TypeVar / TypeAlias / NewType stubs are generated correctly."""

    def test_typevar_stub_in_output(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
        )
        assert "T = TypeVar('T')" in c
        assert_valid_syntax(c)

    def test_newtype_stub_in_output(self):
        c = make_stub(
            "from typing import NewType\n"
            "UserId = NewType('UserId', int)\n"
        )
        assert "UserId = NewType('UserId', int)" in c
        assert_valid_syntax(c)

    def test_typealias_stub_in_output(self):
        c = make_stub(
            "from typing import TypeAlias\n"
            "PathStr: TypeAlias = str\n"
        )
        assert "PathStr: TypeAlias = str" in c
        assert_valid_syntax(c)

    def test_alias_precedes_using_function(self):
        """Alias declaration appears before the function that uses it."""
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "def identity(x: T) -> T: return x\n"
        )
        assert c.index("T = TypeVar") < c.index("def identity")

    def test_alias_respects_all(self):
        c = make_stub(
            "__all__ = ['T', 'helper']\n"
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "S = TypeVar('S')\n"
            "def helper(x: int) -> int: return x\n"
        )
        assert "T = TypeVar" in c
        assert "S = TypeVar" not in c
