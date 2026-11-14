"""Tests for the symbol classes."""
from __future__ import annotations

from stubpy.analysis.harvest import FunctionInfo
from stubpy.analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    SymbolKind,
    VariableSymbol,
)


class TestClassSymbol:
    def test_kind(self):
        assert ClassSymbol("Foo", 1).kind == SymbolKind.CLASS

    def test_fields(self):
        sym = ClassSymbol("Widget", 5)
        assert sym.name == "Widget"
        assert sym.lineno == 5
        assert sym.live_type is None
        assert sym.ast_info is None

    def test_with_live_type(self):
        class MyClass: pass
        sym = ClassSymbol("MyClass", 1, live_type=MyClass)
        assert sym.live_type is MyClass


class TestFunctionSymbol:
    def test_kind(self):
        assert FunctionSymbol("foo", 1).kind == SymbolKind.FUNCTION

    def test_is_async_default_false(self):
        sym = FunctionSymbol("foo", 1)
        assert sym.is_async is False

    def test_is_async_from_ast_info(self):
        fi = FunctionInfo(name="fetch", lineno=1, is_async=True)
        sym = FunctionSymbol("fetch", 1, ast_info=fi)
        assert sym.is_async is True

    def test_is_async_override_when_no_ast_info(self):
        sym = FunctionSymbol("foo", 1, is_async=True)
        assert sym.is_async is True

    def test_ast_info_takes_precedence_for_async(self):
        fi = FunctionInfo(name="foo", lineno=1, is_async=True)
        sym = FunctionSymbol("foo", 1, ast_info=fi, is_async=False)
        assert sym.is_async is True


class TestVariableSymbol:
    def test_kind(self):
        assert VariableSymbol("X", 1).kind == SymbolKind.VARIABLE

    def test_effective_type_annotation_wins(self):
        v = VariableSymbol("X", 1, annotation_str="int", inferred_type_str="float")
        assert v.effective_type_str == "int"

    def test_effective_type_inferred_fallback(self):
        v = VariableSymbol("X", 1, inferred_type_str="str")
        assert v.effective_type_str == "str"

    def test_effective_type_none(self):
        v = VariableSymbol("X", 1)
        assert v.effective_type_str is None


class TestAliasSymbol:
    def test_kind(self):
        assert AliasSymbol("T", 1).kind == SymbolKind.ALIAS


class TestOverloadGroup:
    def test_kind(self):
        assert OverloadGroup("parse", 1).kind == SymbolKind.OVERLOAD

    def test_empty_variants(self):
        g = OverloadGroup("parse", 1)
        assert g.variants == []

    def test_add_variants(self):
        g = OverloadGroup("parse", 1)
        g.variants.append(FunctionSymbol("parse", 2))
        g.variants.append(FunctionSymbol("parse", 4))
        assert len(g.variants) == 2

    def test_live_func(self):
        def impl(x): return x
        g = OverloadGroup("parse", 1, live_func=impl)
        assert g.live_func is impl
