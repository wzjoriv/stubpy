"""Tests for SymbolTable."""
from __future__ import annotations

from stubpy.analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
)


class TestSymbolTable:
    def test_empty(self):
        t = SymbolTable()
        assert len(t) == 0
        assert "Foo" not in t

    def test_add_and_contains(self):
        t = SymbolTable()
        t.add(ClassSymbol("Foo", 1))
        assert "Foo" in t
        assert "Bar" not in t

    def test_get_existing(self):
        t = SymbolTable()
        t.add(ClassSymbol("Foo", 1))
        sym = t.get("Foo")
        assert sym is not None
        assert sym.name == "Foo"

    def test_get_missing(self):
        t = SymbolTable()
        assert t.get("Missing") is None

    def test_get_class(self):
        t = SymbolTable()
        t.add(ClassSymbol("Foo", 1))
        assert t.get_class("Foo") is not None
        assert t.get_class("Foo").kind == SymbolKind.CLASS

    def test_get_class_wrong_kind(self):
        t = SymbolTable()
        t.add(FunctionSymbol("bar", 1))
        assert t.get_class("bar") is None

    def test_get_function(self):
        t = SymbolTable()
        t.add(FunctionSymbol("bar", 1))
        assert t.get_function("bar") is not None

    def test_get_function_wrong_kind(self):
        t = SymbolTable()
        t.add(ClassSymbol("Foo", 1))
        assert t.get_function("Foo") is None

    def test_len(self):
        t = SymbolTable()
        for i in range(5):
            t.add(ClassSymbol(f"C{i}", i))
        assert len(t) == 5

    def test_iteration(self):
        t = SymbolTable()
        t.add(ClassSymbol("A", 1))
        t.add(FunctionSymbol("b", 2))
        items = list(t)
        assert len(items) == 2

    def test_all_names_order(self):
        t = SymbolTable()
        t.add(ClassSymbol("Alpha", 1))
        t.add(FunctionSymbol("beta", 2))
        t.add(VariableSymbol("Gamma", 3))
        assert t.all_names() == ["Alpha", "beta", "Gamma"]

    def test_sorted_by_line(self):
        t = SymbolTable()
        t.add(ClassSymbol("C", 10))
        t.add(ClassSymbol("A", 1))
        t.add(ClassSymbol("B", 5))
        names = [s.name for s in t.sorted_by_line()]
        assert names == ["A", "B", "C"]

    def test_classes_iterator(self):
        t = SymbolTable()
        t.add(ClassSymbol("A", 1))
        t.add(FunctionSymbol("b", 2))
        t.add(ClassSymbol("C", 3))
        classes = list(t.classes())
        assert len(classes) == 2
        assert all(isinstance(c, ClassSymbol) for c in classes)

    def test_functions_iterator(self):
        t = SymbolTable()
        t.add(FunctionSymbol("foo", 1))
        t.add(ClassSymbol("Bar", 2))
        funcs = list(t.functions())
        assert len(funcs) == 1

    def test_variables_iterator(self):
        t = SymbolTable()
        t.add(VariableSymbol("X", 1))
        t.add(ClassSymbol("Y", 2))
        vars_ = list(t.variables())
        assert len(vars_) == 1

    def test_aliases_iterator(self):
        t = SymbolTable()
        t.add(AliasSymbol("T", 1))
        t.add(ClassSymbol("Foo", 2))
        aliases = list(t.aliases())
        assert len(aliases) == 1

    def test_overload_groups_iterator(self):
        t = SymbolTable()
        t.add(OverloadGroup("parse", 1))
        t.add(ClassSymbol("Foo", 2))
        groups = list(t.overload_groups())
        assert len(groups) == 1

    def test_by_kind(self):
        t = SymbolTable()
        t.add(ClassSymbol("A", 1))
        t.add(FunctionSymbol("b", 2))
        result = list(t.by_kind(SymbolKind.CLASS))
        assert len(result) == 1 and result[0].name == "A"

    def test_repr(self):
        t = SymbolTable()
        t.add(ClassSymbol("Foo", 1))
        r = repr(t)
        assert "SymbolTable" in r and "Foo" in r

    def test_name_overwrite_in_index(self):
        t = SymbolTable()
        t.add(ClassSymbol("X", 1))
        t.add(FunctionSymbol("X", 2))
        assert t.get("X").kind == SymbolKind.FUNCTION
        assert len(list(t)) == 2
