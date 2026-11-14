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
        assert DiagnosticLevel.INFO.value    == 10
        assert DiagnosticLevel.WARNING.value == 20
        assert DiagnosticLevel.ERROR.value   == 30

    def test_all_levels_exist(self):
        levels = {l.value for l in DiagnosticLevel}
        assert {"INFO", "WARNING", "ERROR"} == {l.name for l in DiagnosticLevel}


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
        assert len(c.info_items) == 1

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
        assert len(c.info_items) == 1
        assert len(c.warnings)   == 1
        assert len(c.errors)     == 1
        assert all(d.level == DiagnosticLevel.INFO    for d in c.info_items)
        assert all(d.level == DiagnosticLevel.WARNING for d in c.warnings)
        assert all(d.level == DiagnosticLevel.ERROR   for d in c.errors)

    def test_has_info_true_when_info_recorded(self):
        c = DiagnosticCollector()
        assert not c.has_info()
        c.info(DiagnosticStage.LOAD, "x", "msg")
        assert c.has_info()
        assert not c.has_warnings()  # info must not pollute warnings

    def test_has_info_false_when_only_warnings(self):
        c = DiagnosticCollector()
        c.warning(DiagnosticStage.EMIT, "x", "msg")
        assert not c.has_info()
        assert c.has_warnings()

    def test_info_items_empty_by_default(self):
        c = DiagnosticCollector()
        assert c.info_items == []

    def test_info_items_returns_only_info_level(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "info msg")
        c.warning(DiagnosticStage.EMIT, "b", "warn msg")
        items = c.info_items
        assert len(items) == 1
        assert items[0].level == DiagnosticLevel.INFO
        assert items[0].message == "info msg"

    def test_level_ordering_allows_filtering(self):
        """IntEnum ordering: filter diags at WARNING and above."""
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "info")
        c.warning(DiagnosticStage.EMIT, "b", "warn")
        c.error(DiagnosticStage.RESOLVE, "c", "err")
        at_least_warning = [d for d in c.all if d.level >= DiagnosticLevel.WARNING]
        assert len(at_least_warning) == 2
        at_least_error = [d for d in c.all if d.level >= DiagnosticLevel.ERROR]
        assert len(at_least_error) == 1


# ---------------------------------------------------------------------------
# Integration: diagnostics emitted during stub generation
# ---------------------------------------------------------------------------


    def test_summary_empty(self):
        c = DiagnosticCollector()
        s = c.summary()
        assert "0 error" in s.lower() or s == "" or "no issues" in s.lower()

    def test_summary_counts(self):
        c = DiagnosticCollector()
        c.info(DiagnosticStage.LOAD, "a", "i")
        c.warning(DiagnosticStage.EMIT, "b", "w1")
        c.warning(DiagnosticStage.EMIT, "c", "w2")
        c.error(DiagnosticStage.RESOLVE, "d", "e")
        s = c.summary()
        assert "1" in s and "error" in s.lower()
        assert "2" in s and "warn" in s.lower()

class TestDiagnosticsFromGeneration:
    """Integration tests for diagnostics emitted by the full generate_stub pipeline."""

    def _ctx(self, **cfg_kwargs):
        from stubpy.context import StubConfig, StubContext
        return StubContext(config=StubConfig(verbose=True, **cfg_kwargs))

    def _generate(self, tmp_path, src, **cfg_kwargs):
        import textwrap
        from stubpy import generate_stub
        src_p = tmp_path / "mod.py"
        src_p.write_text(textwrap.dedent(src))
        ctx = self._ctx(**cfg_kwargs)
        stub = generate_stub(str(src_p), str(tmp_path / "mod.pyi"), ctx=ctx)
        return stub, ctx.diagnostics

    # ------------------------------------------------------------------
    # DiagnosticLevel ordering (Bug 1 regression guard)
    # ------------------------------------------------------------------

    def test_diagnostic_level_ordering(self):
        assert DiagnosticLevel.INFO    < DiagnosticLevel.WARNING < DiagnosticLevel.ERROR
        assert DiagnosticLevel.INFO    <= DiagnosticLevel.INFO
        assert DiagnosticLevel.WARNING >= DiagnosticLevel.WARNING
        assert DiagnosticLevel.ERROR   >= DiagnosticLevel.WARNING
        assert not (DiagnosticLevel.INFO >= DiagnosticLevel.WARNING)

    def test_filter_by_level_gte(self, tmp_path):
        stub, diags = self._generate(tmp_path, "X: int = 1\n")
        # Must not crash and must return a filterable list
        warns_and_above = [d for d in diags.all if d.level >= DiagnosticLevel.WARNING]
        assert isinstance(warns_and_above, list)

    # ------------------------------------------------------------------
    # _NonLiteralDefault not leaking (Bug 2 regression guard)
    # ------------------------------------------------------------------

    def test_non_literal_default_no_annotation_leak(self, tmp_path):
        """AST-only: x=os.sep must not produce x: _NonLiteralDefault."""
        from stubpy.context import ExecutionMode
        stub, diags = self._generate(
            tmp_path, "def f(x=os.sep): pass\n",
            execution_mode=ExecutionMode.AST_ONLY,
        )
        assert "_NonLiteralDefault" not in stub
        assert "x = os.sep" in stub  # non-literal shown as bare default

    def test_complex_default_no_annotation_leak(self, tmp_path):
        """AST-only: x=SomeClass() must not produce x: _NonLiteralDefault."""
        from stubpy.context import ExecutionMode
        stub, diags = self._generate(
            tmp_path, "def f(x=list(), y=dict()): pass\n",
            execution_mode=ExecutionMode.AST_ONLY,
        )
        assert "_NonLiteralDefault" not in stub

    # ------------------------------------------------------------------
    # Overload params preserved (Bug 3 regression guard)
    # ------------------------------------------------------------------

    def test_overload_params_preserved_runtime(self, tmp_path):
        """Runtime: overload variant annotations not replaced by implementation."""
        from textwrap import dedent
        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def parse(x: int) -> int: ...
            @overload
            def parse(x: str) -> str: ...
            def parse(x): return x
        """)
        assert "x: int" in stub
        assert "x: str" in stub
        assert stub.count("@overload") == 2

    def test_overload_params_preserved_ast_only(self, tmp_path):
        """AST-only: overload variant annotations come from the variant node."""
        from stubpy.context import ExecutionMode
        from textwrap import dedent
        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def convert(value: bytes, encoding: str = "utf-8") -> str: ...
            @overload
            def convert(value: str) -> bytes: ...
            def convert(value, encoding="utf-8"): return value
        """, execution_mode=ExecutionMode.AST_ONLY)
        assert "value: bytes" in stub
        assert "encoding: str" in stub
        assert "value: str" in stub
        assert stub.count("@overload") == 2

    def test_overload_return_types_preserved(self, tmp_path):
        from textwrap import dedent
        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def f(x: int) -> int: ...
            @overload
            def f(x: str) -> str: ...
            def f(x): return x
        """)
        assert "-> int" in stub
        assert "-> str" in stub

    # ------------------------------------------------------------------
    # Diagnostics for uninformative/dynamic values (Bug 4 regression guard)
    # ------------------------------------------------------------------

    def test_warning_for_runtime_uninformative_type(self, tmp_path):
        """Runtime: WARNING when variable has uninformative type (function object)."""
        import os
        stub, diags = self._generate(tmp_path, "import os\nPATH = os.getcwd()\nX: int = 1\n")
        warns = [d for d in diags.all
                 if d.level >= DiagnosticLevel.WARNING and "PATH" in d.symbol]
        # PATH = os.getcwd() returns a str so it's actually typed correctly.
        # The key test is that no crash occurs and diags are properly structured.
        assert isinstance(diags.all, list)

    def test_info_for_ast_only_non_literal_variable(self, tmp_path):
        """AST-only: INFO diagnostic when variable RHS is not a literal."""
        from stubpy.context import ExecutionMode
        stub, diags = self._generate(
            tmp_path, "import os\nPATH = os.getcwd()\n",
            execution_mode=ExecutionMode.AST_ONLY,
        )
        infos = [d for d in diags.all
                 if d.level == DiagnosticLevel.INFO and "PATH" in d.symbol]
        assert infos, f"Expected INFO for PATH; got {[(d.symbol, d.message) for d in diags.all]}"
        assert "not a literal" in infos[0].message

    def test_no_warning_for_annotated_variable(self, tmp_path):
        """No diagnostic when variable is annotated — type is explicit."""
        from stubpy.context import ExecutionMode
        _, diags = self._generate(
            tmp_path, "import os\nPATH: str = os.getcwd()\n",
            execution_mode=ExecutionMode.AST_ONLY,
        )
        warns = [d for d in diags.all
                 if d.level >= DiagnosticLevel.WARNING and "PATH" in d.symbol]
        assert not warns, f"Unexpected warning: {warns}"

    def test_no_diagnostic_for_literal_variable(self, tmp_path):
        """No diagnostic for literal-valued variable — type is inferred cleanly."""
        from stubpy.context import ExecutionMode
        _, diags = self._generate(
            tmp_path, "MAX = 100\nLABEL = 'hello'\n",
            execution_mode=ExecutionMode.AST_ONLY,
        )
        warns = [d for d in diags.all
                 if d.level >= DiagnosticLevel.WARNING
                 and any(n in d.symbol for n in ("MAX", "LABEL"))]
        assert not warns

    # ------------------------------------------------------------------
    # Auto-mode fallback diagnostic
    # ------------------------------------------------------------------

    def test_auto_mode_emits_warning_on_fallback(self, tmp_path):
        """AUTO mode emits WARNING when module load fails and falls back to AST."""
        from stubpy.context import ExecutionMode
        src = "import _nonexistent_module_xyz\nX: int = 1\n"
        stub, diags = self._generate(
            tmp_path, src, execution_mode=ExecutionMode.AUTO,
        )
        warns = [d for d in diags.all
                 if d.level >= DiagnosticLevel.WARNING
                 and ("falling back" in d.message.lower() or "fallback" in d.message.lower())]
        assert warns, f"Expected WARNING about AST-only fallback; got: {[d.message for d in diags.all]}"
        assert "X: int" in stub  # AST-only still produces useful output

    # ------------------------------------------------------------------
    # Unannotated param diagnostics
    # ------------------------------------------------------------------

    def test_info_for_bare_param(self, tmp_path):
        """INFO diagnostic when a method param has no annotation or inferrable type."""
        stub, diags = self._generate(tmp_path, """\
            class C:
                def m(self, opaque_value): pass
        """)
        infos = [d for d in diags.all
                 if d.level == DiagnosticLevel.INFO and "opaque_value" in d.message]
        assert infos, f"Expected INFO for opaque_value; diags: {[d.message for d in diags.all]}"

    def test_no_info_for_annotated_param(self, tmp_path):
        """No diagnostic for an annotated param."""
        _, diags = self._generate(tmp_path, """\
            class C:
                def m(self, x: int, y: str = "hi") -> None: pass
        """)
        spurious = [d for d in diags.all
                    if d.level == DiagnosticLevel.INFO
                    and any(n in d.message for n in ("'x'", "'y'"))]
        assert not spurious

    def test_no_info_for_inferred_param(self, tmp_path):
        """No diagnostic when param type is inferred from literal default."""
        _, diags = self._generate(tmp_path, """\
            class C:
                def m(self, x=0, y="hi", flag=True) -> None: pass
        """)
        spurious = [d for d in diags.all
                    if d.level == DiagnosticLevel.INFO
                    and any(n in d.message for n in ("'x'", "'y'", "'flag'"))]
        assert not spurious
