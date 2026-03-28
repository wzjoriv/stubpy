"""
tests/test_diagnostics.py
--------------------------
Unit tests for stubpy.diagnostics:
  - Diagnostic (frozen dataclass)
  - DiagnosticLevel (enum)
  - DiagnosticStage (enum)
  - DiagnosticCollector
"""
from __future__ import annotations
from stubpy.diagnostics import (
    Diagnostic, DiagnosticCollector, DiagnosticLevel, DiagnosticStage,
)


class TestDiagnosticLevels:
    def test_level_values(self):
        assert DiagnosticLevel.INFO.value    == "INFO"
        assert DiagnosticLevel.WARNING.value == "WARNING"
        assert DiagnosticLevel.ERROR.value   == "ERROR"

    def test_all_levels_exist(self):
        levels = {l.value for l in DiagnosticLevel}
        assert {"INFO", "WARNING", "ERROR"} == levels


class TestDiagnosticStages:
    def test_all_stages_exist(self):
        expected = {"load", "ast_pass", "symbol_table", "alias",
                    "resolve", "emit", "import", "generator"}
        actual = {s.value for s in DiagnosticStage}
        assert expected == actual

    def test_stage_values(self):
        assert DiagnosticStage.LOAD.value         == "load"
        assert DiagnosticStage.AST_PASS.value     == "ast_pass"
        assert DiagnosticStage.SYMBOL_TABLE.value == "symbol_table"
        assert DiagnosticStage.ALIAS.value        == "alias"
        assert DiagnosticStage.RESOLVE.value      == "resolve"
        assert DiagnosticStage.EMIT.value         == "emit"
        assert DiagnosticStage.IMPORT.value       == "import"
        assert DiagnosticStage.GENERATOR.value    == "generator"


class TestDiagnosticRecord:
    def _make(self, level=DiagnosticLevel.ERROR, stage=DiagnosticStage.EMIT,
              symbol="Foo", message="bad"):
        return Diagnostic(level=level, stage=stage, symbol=symbol, message=message)

    def test_fields(self):
        d = self._make()
        assert d.level   == DiagnosticLevel.ERROR
        assert d.stage   == DiagnosticStage.EMIT
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
        d = self._make(level=DiagnosticLevel.WARNING, stage=DiagnosticStage.RESOLVE,
                       symbol="Bar", message="warn msg")
        s = str(d)
        assert "[WARNING]" in s
        assert "(resolve)" in s
        assert "Bar"       in s
        assert "warn msg"  in s

    def test_is_frozen(self):
        d = self._make()
        try:
            d.message = "changed"
            assert False, "Should be frozen (AttributeError or TypeError expected)"
        except (AttributeError, TypeError):
            pass

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
        c.info(DiagnosticStage.LOAD, "f.py", "loaded")
        assert len(c) == 1
        assert not c.has_errors()
        assert not c.has_warnings()
        assert len(c.infos) == 1

    def test_add_warning(self):
        c = DiagnosticCollector()
        c.warning(DiagnosticStage.RESOLVE, "Foo", "warn")
        assert c.has_warnings()
        assert not c.has_errors()
        assert len(c.warnings) == 1

    def test_add_error(self):
        c = DiagnosticCollector()
        c.error(DiagnosticStage.EMIT, "Bar", "err")
        assert c.has_errors()
        assert len(c.errors) == 1

    def test_all_levels_together(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "f.py", "loaded")
        c.warning(DiagnosticStage.RESOLVE, "Foo", "warn")
        c.error(DiagnosticStage.EMIT, "Bar", "err")
        assert len(c) == 3
        assert c.summary() == "1 errors, 1 warnings, 1 infos"

    def test_by_stage(self):
        c = DiagnosticCollector()
        c.error(DiagnosticStage.LOAD, "x", "m1")
        c.warning(DiagnosticStage.EMIT, "y", "m2")
        c.info(DiagnosticStage.LOAD, "z", "m3")
        assert len(c.by_stage(DiagnosticStage.LOAD)) == 2
        assert len(c.by_stage(DiagnosticStage.EMIT)) == 1
        assert len(c.by_stage(DiagnosticStage.RESOLVE)) == 0

    def test_by_symbol(self):
        c = DiagnosticCollector()
        c.error(DiagnosticStage.EMIT, "Alpha", "m1")
        c.warning(DiagnosticStage.EMIT, "Alpha", "m2")
        c.info(DiagnosticStage.LOAD, "Beta", "m3")
        assert len(c.by_symbol("Alpha")) == 2
        assert len(c.by_symbol("Beta")) == 1
        assert len(c.by_symbol("Missing")) == 0

    def test_clear(self):
        c = DiagnosticCollector()
        c.error(DiagnosticStage.EMIT, "X", "e")
        c.clear()
        assert len(c) == 0
        assert not c.has_errors()

    def test_iteration(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "x")
        c.info(DiagnosticStage.LOAD, "b", "y")
        items = list(c)
        assert len(items) == 2
        assert all(isinstance(i, Diagnostic) for i in items)

    def test_bool_empty(self):
        c = DiagnosticCollector()
        assert not bool(c)

    def test_bool_nonempty(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "x", "y")
        assert bool(c)

    def test_format_all(self):
        c = DiagnosticCollector()
        c.warning(DiagnosticStage.RESOLVE, "Foo", "test msg")
        s = c.format_all()
        assert "WARNING" in s and "Foo" in s and "test msg" in s

    def test_all_returns_copy(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "x")
        lst = c.all
        lst.append(None)
        assert len(c) == 1  # mutation of copy doesn't affect collector

    def test_ordering_preserved(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "first", "1")
        c.warning(DiagnosticStage.EMIT, "second", "2")
        c.error(DiagnosticStage.RESOLVE, "third", "3")
        items = list(c)
        assert items[0].symbol == "first"
        assert items[1].symbol == "second"
        assert items[2].symbol == "third"

    def test_add_method_direct(self):
        c = DiagnosticCollector()
        c.add(DiagnosticLevel.ERROR, DiagnosticStage.LOAD, "X", "direct add")
        assert c.has_errors()
        assert c.errors[0].message == "direct add"

    def test_errors_infos_warnings_are_filtered_views(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "i")
        c.warning(DiagnosticStage.EMIT, "b", "w")
        c.error(DiagnosticStage.RESOLVE, "c", "e")
        assert len(c.infos)    == 1
        assert len(c.warnings) == 1
        assert len(c.errors)   == 1
        assert all(d.level == DiagnosticLevel.INFO    for d in c.infos)
        assert all(d.level == DiagnosticLevel.WARNING for d in c.warnings)
        assert all(d.level == DiagnosticLevel.ERROR   for d in c.errors)
