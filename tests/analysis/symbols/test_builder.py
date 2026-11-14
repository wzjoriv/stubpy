"""Tests for build_symbol_table."""
from __future__ import annotations

import types as _t

from stubpy.analysis.harvest import ast_harvest
from stubpy.analysis.symbols import (
    SymbolKind,
    build_symbol_table,
)


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
        Imported.__module__ = "some.other.module"
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


class TestBuildSymbolTableDiagnostics:
    """build_symbol_table now accepts a diagnostics= parameter."""

    def test_diagnostics_param_accepted(self):
        from stubpy.analysis.harvest import ast_harvest
        from stubpy.analysis.symbols import build_symbol_table
        from stubpy.core.diagnostics import DiagnosticCollector
        syms = ast_harvest("X = 1\n")
        dc = DiagnosticCollector()
        tbl = build_symbol_table(None, "_m", syms, diagnostics=dc)
        assert tbl is not None

    def test_non_literal_variable_emits_info(self):
        """AST-only: non-literal RHS emits INFO diagnostic for the variable."""
        from stubpy.analysis.harvest import ast_harvest
        from stubpy.analysis.symbols import build_symbol_table
        from stubpy.core.diagnostics import DiagnosticCollector, Level
        syms = ast_harvest("PATH = os.getcwd()\n")
        dc = DiagnosticCollector()
        build_symbol_table(None, "_m", syms, diagnostics=dc)
        infos = [d for d in dc.all if d.level == Level.INFO
                 and "PATH" in d.symbol]
        assert infos, f"Expected INFO for PATH; got {[d.message for d in dc.all]}"
        assert "not a literal" in infos[0].message

    def test_literal_variable_no_diagnostic(self):
        """Literal-valued variable should not emit any diagnostic."""
        from stubpy.analysis.harvest import ast_harvest
        from stubpy.analysis.symbols import build_symbol_table
        from stubpy.core.diagnostics import DiagnosticCollector, Level
        syms = ast_harvest("X = 42\n")
        dc = DiagnosticCollector()
        build_symbol_table(None, "_m", syms, diagnostics=dc)
        warns = [d for d in dc.all if d.level >= Level.WARNING
                 and "X" in d.symbol]
        assert not warns

    def test_no_diagnostics_param_does_not_crash(self):
        """Omitting diagnostics= is still valid (default None)."""
        from stubpy.analysis.harvest import ast_harvest
        from stubpy.analysis.symbols import build_symbol_table
        syms = ast_harvest("PATH = os.getcwd()\n")
        tbl = build_symbol_table(None, "_m", syms)
        assert tbl is not None
