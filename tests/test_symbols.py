"""
tests/test_symbols.py
---------------------
Unit tests for stubpy.symbols:
  - StubSymbol hierarchy
  - SymbolTable
  - build_symbol_table()
"""
from __future__ import annotations
import types as _t

from stubpy.ast_pass import FunctionInfo, ast_harvest
from stubpy.symbols import (
    AliasSymbol, ClassSymbol, FunctionSymbol, OverloadGroup,
    StubSymbol, SymbolKind, SymbolTable, VariableSymbol, build_symbol_table,
)


# ---------------------------------------------------------------------------
# Symbol class tests
# ---------------------------------------------------------------------------

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
        assert sym.is_async is True  # ast_info wins


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


# ---------------------------------------------------------------------------
# SymbolTable tests
# ---------------------------------------------------------------------------

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
        # Last write wins in the index
        assert t.get("X").kind == SymbolKind.FUNCTION
        # Both are still in ordered list
        assert len(list(t)) == 2


# ---------------------------------------------------------------------------
# build_symbol_table tests
# ---------------------------------------------------------------------------

def _make_module(name: str, **attrs) -> _t.ModuleType:
    m = _t.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


class TestBuildSymbolTable:
    def test_class_symbols_built(self):
        src = "class Foo: pass\nclass Bar: pass\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst1")
        class Foo: pass
        class Bar: pass
        Foo.__module__ = Bar.__module__ = "_stubpy_target_bst1"
        m.Foo, m.Bar = Foo, Bar
        tbl = build_symbol_table(m, "_stubpy_target_bst1", syms)
        assert "Foo" in tbl and "Bar" in tbl
        assert tbl.get_class("Foo").live_type is Foo

    def test_class_has_ast_info(self):
        src = "class Widget(object): pass\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst_ai")
        class Widget: pass
        Widget.__module__ = "_stubpy_target_bst_ai"
        m.Widget = Widget
        tbl = build_symbol_table(m, "_stubpy_target_bst_ai", syms)
        sym = tbl.get_class("Widget")
        assert sym.ast_info is not None
        assert sym.ast_info.name == "Widget"

    def test_function_symbols_built(self):
        src = "def greet(name: str) -> str: ...\nasync def fetch() -> None: ...\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst2")
        def greet(n): return n
        async def fetch(): pass
        m.greet, m.fetch = greet, fetch
        tbl = build_symbol_table(m, "_stubpy_target_bst2", syms)
        assert "greet" in tbl
        assert "fetch" in tbl
        assert tbl.get_function("fetch").is_async is True
        assert tbl.get_function("greet").is_async is False

    def test_variable_symbols_built(self):
        src = "MAX: int = 42\nNAME = 'test'\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst3", MAX=42, NAME="test")
        tbl = build_symbol_table(m, "_stubpy_target_bst3", syms)
        assert "MAX" in tbl and "NAME" in tbl
        max_sym = next(v for v in tbl.variables() if v.name == "MAX")
        assert max_sym.annotation_str == "int"
        assert max_sym.live_value == 42
        name_sym = next(v for v in tbl.variables() if v.name == "NAME")
        assert name_sym.annotation_str is None
        assert name_sym.inferred_type_str == "str"

    def test_alias_symbols_built(self):
        from typing import TypeVar
        src = "from typing import TypeVar\nT = TypeVar('T')\n"
        syms = ast_harvest(src)
        T = TypeVar("T")
        m = _make_module("_stubpy_target_bst4", T=T)
        tbl = build_symbol_table(m, "_stubpy_target_bst4", syms)
        assert "T" in tbl
        assert tbl.get("T").kind == SymbolKind.ALIAS

    def test_all_exports_filter(self):
        src = "class Pub: pass\nclass Priv: pass\nPUB = 1\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst5")
        class Pub: pass
        class Priv: pass
        Pub.__module__ = Priv.__module__ = "_stubpy_target_bst5"
        m.Pub, m.Priv, m.PUB = Pub, Priv, 1
        tbl = build_symbol_table(m, "_stubpy_target_bst5", syms, all_exports={"Pub"})
        assert "Pub" in tbl
        assert "Priv" not in tbl
        assert "PUB" not in tbl

    def test_no_all_exports_includes_all_public(self):
        src = "class Pub: pass\nPUB = 1\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst5b")
        class Pub: pass
        Pub.__module__ = "_stubpy_target_bst5b"
        m.Pub, m.PUB = Pub, 1
        tbl = build_symbol_table(m, "_stubpy_target_bst5b", syms, all_exports=None)
        assert "Pub" in tbl and "PUB" in tbl

    def test_private_symbols_filtered(self):
        src = "_PRIV = 1\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst6", _PRIV=1)
        tbl = build_symbol_table(m, "_stubpy_target_bst6", syms)
        assert "_PRIV" not in tbl

    def test_overload_group_built(self):
        src = (
            "from typing import overload\n"
            "@overload\ndef parse(x: int) -> int: ...\n"
            "@overload\ndef parse(x: str) -> str: ...\n"
            "def parse(x): ...\n"
        )
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_bst7")
        def parse(x): return x
        m.parse = parse
        tbl = build_symbol_table(m, "_stubpy_target_bst7", syms)
        assert "parse" in tbl
        groups = list(tbl.overload_groups())
        assert len(groups) == 1
        assert len(groups[0].variants) == 2

    def test_ast_only_mode_live_type_none(self):
        src = "class Foo: pass\n"
        syms = ast_harvest(src)
        tbl = build_symbol_table(None, "_stubpy_target_none", syms)
        assert "Foo" in tbl
        assert tbl.get_class("Foo").live_type is None

    def test_foreign_class_not_included(self):
        """Classes from other modules are excluded."""
        src = "class Local: pass\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_foreign")
        class Local: pass
        class Imported: pass
        Local.__module__ = "_stubpy_target_foreign"
        Imported.__module__ = "some.other.module"  # foreign
        m.Local, m.Imported = Local, Imported
        tbl = build_symbol_table(m, "_stubpy_target_foreign", syms)
        assert "Local" in tbl
        assert "Imported" not in tbl

    def test_source_order_preserved(self):
        src = "class B: pass\nclass A: pass\n"
        syms = ast_harvest(src)
        m = _make_module("_stubpy_target_order")
        class B: pass
        class A: pass
        B.__module__ = A.__module__ = "_stubpy_target_order"
        m.A, m.B = A, B
        tbl = build_symbol_table(m, "_stubpy_target_order", syms)
        names = [s.name for s in tbl.sorted_by_line()]
        assert names.index("B") < names.index("A")
