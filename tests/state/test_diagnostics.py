"""Tests for stubpy.state.diagnostics."""
from __future__ import annotations

import pytest

from stubpy.state.diagnostics import Diagnostic, DiagnosticCollector, Level, Stage


class TestDiagnosticLevels:
    def test_level_values(self):
        assert Level.INFO.value    == 10
        assert Level.WARNING.value == 20
        assert Level.ERROR.value   == 30

    def test_all_levels_exist(self):
        assert {"INFO", "WARNING", "ERROR"} == {l.name for l in Level}


class TestDiagnosticStages:
    def test_all_stages_exist(self):
        expected = {"load", "ast_pass", "symbol_table", "alias",
                    "resolve", "emit", "import", "generator", "typecheck"}
        actual = {s.value for s in Stage}
        assert expected == actual

    def test_stage_values(self):
        assert Stage.LOAD.value         == "load"
        assert Stage.AST_PASS.value     == "ast_pass"
        assert Stage.SYMBOL_TABLE.value == "symbol_table"
        assert Stage.ALIAS.value        == "alias"
        assert Stage.RESOLVE.value      == "resolve"
        assert Stage.EMIT.value         == "emit"
        assert Stage.IMPORT.value       == "import"
        assert Stage.GENERATOR.value    == "generator"


class TestDiagnosticRecord:
    def _make(self, level=Level.ERROR, stage=Stage.EMIT,
              symbol="Foo", message="bad"):
        return Diagnostic(level=level, stage=stage, symbol=symbol, message=message)

    def test_fields(self):
        d = self._make()
        assert d.level   == Level.ERROR
        assert d.stage   == Stage.EMIT
        assert d.symbol  == "Foo"
        assert d.message == "bad"

    def test_str_format(self):
        d = self._make()
        s = str(d)
        assert "[ERROR]" in s
        assert "(emit)"  in s
        assert "Foo"     in s
        assert "bad"     in s

    def test_str_warning_format(self):
        d = self._make(level=Level.WARNING, stage=Stage.RESOLVE,
                       symbol="Bar", message="warn msg")
        s = str(d)
        assert "[WARNING]" in s
        assert "(resolve)" in s
        assert "Bar"       in s
        assert "warn msg"  in s

    def test_is_frozen(self):
        d = self._make()
        with pytest.raises((AttributeError, TypeError)):
            d.message = "changed"

    def test_equality(self):
        d1 = self._make()
        d2 = self._make()
        assert d1 == d2

    def test_inequality(self):
        d1 = self._make(message="a")
        d2 = self._make(message="b")
        assert d1 != d2

    def test_hashable(self):
        d = self._make()
        s = {d}
        assert d in s


class TestDiagnosticCollector:
    def test_empty(self):
        c = DiagnosticCollector()
        assert len(c) == 0
        assert not c.has_errors()
        assert not c.has_warnings()
        assert c.summary() == "0 errors, 0 warnings, 0 infos"

    def test_add_info(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "f.py", "loaded")
        assert len(c) == 1
        assert not c.has_errors()
        assert not c.has_warnings()
        assert len(c.info_items) == 1

    def test_add_warning(self):
        c = DiagnosticCollector()
        c.warning(Stage.RESOLVE, "Foo", "warn")
        assert c.has_warnings()
        assert not c.has_errors()
        assert len(c.warnings) == 1

    def test_add_error(self):
        c = DiagnosticCollector()
        c.error(Stage.EMIT, "Bar", "err")
        assert c.has_errors()
        assert len(c.errors) == 1

    def test_all_levels_together(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "f.py", "loaded")
        c.warning(Stage.RESOLVE, "Foo", "warn")
        c.error(Stage.EMIT, "Bar", "err")
        assert len(c) == 3
        assert c.summary() == "1 errors, 1 warnings, 1 infos"

    def test_by_stage(self):
        c = DiagnosticCollector()
        c.error(Stage.LOAD, "x", "m1")
        c.warning(Stage.EMIT, "y", "m2")
        c.info(Stage.LOAD, "z", "m3")
        assert len(c.by_stage(Stage.LOAD)) == 2
        assert len(c.by_stage(Stage.EMIT)) == 1
        assert len(c.by_stage(Stage.RESOLVE)) == 0

    def test_by_symbol(self):
        c = DiagnosticCollector()
        c.error(Stage.EMIT, "Alpha", "m1")
        c.warning(Stage.EMIT, "Alpha", "m2")
        c.info(Stage.LOAD, "Beta", "m3")
        assert len(c.by_symbol("Alpha")) == 2
        assert len(c.by_symbol("Beta")) == 1
        assert len(c.by_symbol("Missing")) == 0

    def test_clear(self):
        c = DiagnosticCollector()
        c.error(Stage.EMIT, "X", "e")
        c.clear()
        assert len(c) == 0
        assert not c.has_errors()

    def test_iteration(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "x")
        c.info(Stage.LOAD, "b", "y")
        items = list(c)
        assert len(items) == 2
        assert all(isinstance(i, Diagnostic) for i in items)

    def test_bool_empty(self):
        c = DiagnosticCollector()
        assert not bool(c)

    def test_bool_nonempty(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "x", "y")
        assert bool(c)

    def test_format_all(self):
        c = DiagnosticCollector()
        c.warning(Stage.RESOLVE, "Foo", "test msg")
        s = c.format_all()
        assert "WARNING" in s and "Foo" in s and "test msg" in s

    def test_all_returns_copy(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "x")
        lst = c.all
        lst.append(None)
        assert len(c) == 1

    def test_ordering_preserved(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "first", "1")
        c.warning(Stage.EMIT, "second", "2")
        c.error(Stage.RESOLVE, "third", "3")
        items = list(c)
        assert items[0].symbol == "first"
        assert items[1].symbol == "second"
        assert items[2].symbol == "third"

    def test_add_method_direct(self):
        c = DiagnosticCollector()
        c.add(Level.ERROR, Stage.LOAD, "X", "direct add")
        assert c.has_errors()
        assert c.errors[0].message == "direct add"

    def test_errors_infos_warnings_are_filtered_views(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "i")
        c.warning(Stage.EMIT, "b", "w")
        c.error(Stage.RESOLVE, "c", "e")
        assert len(c.info_items) == 1
        assert len(c.warnings)   == 1
        assert len(c.errors)     == 1
        assert all(d.level == Level.INFO    for d in c.info_items)
        assert all(d.level == Level.WARNING for d in c.warnings)
        assert all(d.level == Level.ERROR   for d in c.errors)

    def test_has_info_true_when_info_recorded(self):
        c = DiagnosticCollector()
        assert not c.has_info()
        c.info(Stage.LOAD, "x", "msg")
        assert c.has_info()
        assert not c.has_warnings()

    def test_has_info_false_when_only_warnings(self):
        c = DiagnosticCollector()
        c.warning(Stage.EMIT, "x", "msg")
        assert not c.has_info()
        assert c.has_warnings()

    def test_info_items_empty_by_default(self):
        c = DiagnosticCollector()
        assert c.info_items == []

    def test_info_items_returns_only_info_level(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "info msg")
        c.warning(Stage.EMIT, "b", "warn msg")
        items = c.info_items
        assert len(items) == 1
        assert items[0].level == Level.INFO
        assert items[0].message == "info msg"

    def test_level_ordering_allows_filtering(self):
        """IntEnum ordering: filter diags at WARNING and above."""
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "info")
        c.warning(Stage.EMIT, "b", "warn")
        c.error(Stage.RESOLVE, "c", "err")
        at_least_warning = [d for d in c.all if d.level >= Level.WARNING]
        assert len(at_least_warning) == 2
        at_least_error = [d for d in c.all if d.level >= Level.ERROR]
        assert len(at_least_error) == 1

    def test_summary_empty(self):
        c = DiagnosticCollector()
        s = c.summary()
        assert "0 error" in s.lower() or s == "" or "no issues" in s.lower()

    def test_summary_counts(self):
        c = DiagnosticCollector()
        c.info(Stage.LOAD, "a", "i")
        c.warning(Stage.EMIT, "b", "w1")
        c.warning(Stage.EMIT, "c", "w2")
        c.error(Stage.RESOLVE, "d", "e")
        s = c.summary()
        assert "1" in s and "error" in s.lower()
        assert "2" in s and "warn" in s.lower()
