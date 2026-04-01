"""
tests/test_context.py
-----------------------------
Tests for stubpy.context configuration and diagnostics:
  - ExecutionMode
  - StubConfig
  - StubContext new fields (diagnostics, config, symbol_table, all_exports)
"""
from __future__ import annotations
from stubpy.context import AliasEntry, ExecutionMode, StubConfig, StubContext
from stubpy.diagnostics import DiagnosticCollector, DiagnosticLevel, DiagnosticStage


class TestExecutionMode:
    def test_all_modes_exist(self):
        modes = {m.value for m in ExecutionMode}
        assert {"runtime", "ast_only", "auto"} == modes

    def test_default_is_runtime(self):
        cfg = StubConfig()
        assert cfg.execution_mode == ExecutionMode.RUNTIME


class TestStubConfig:
    def test_defaults(self):
        cfg = StubConfig()
        assert cfg.execution_mode  == ExecutionMode.RUNTIME
        assert cfg.include_private is False
        assert cfg.respect_all     is True
        assert cfg.verbose         is False
        assert cfg.strict          is False

    def test_custom(self):
        cfg = StubConfig(
            execution_mode=ExecutionMode.AST_ONLY,
            include_private=True,
            respect_all=False,
            verbose=True,
            strict=True,
        )
        assert cfg.execution_mode  == ExecutionMode.AST_ONLY
        assert cfg.include_private is True
        assert cfg.respect_all     is False
        assert cfg.verbose         is True
        assert cfg.strict          is True

    def test_all_execution_modes(self):
        for mode in ExecutionMode:
            cfg = StubConfig(execution_mode=mode)
            assert cfg.execution_mode == mode


class TestStubContext:
    def test_fresh_context_has_diagnostics(self):
        ctx = StubContext()
        assert isinstance(ctx.diagnostics, DiagnosticCollector)
        assert not ctx.diagnostics.has_errors()

    def test_fresh_context_has_config(self):
        ctx = StubContext()
        assert isinstance(ctx.config, StubConfig)
        assert ctx.config.execution_mode == ExecutionMode.RUNTIME

    def test_fresh_context_symbol_table_none(self):
        ctx = StubContext()
        assert ctx.symbol_table is None

    def test_fresh_context_all_exports_none(self):
        ctx = StubContext()
        assert ctx.all_exports is None

    def test_custom_config(self):
        cfg = StubConfig(execution_mode=ExecutionMode.AST_ONLY)
        ctx = StubContext(config=cfg)
        assert ctx.config.execution_mode == ExecutionMode.AST_ONLY

    def test_diagnostics_independent_per_instance(self):
        ctx1 = StubContext()
        ctx2 = StubContext()
        ctx1.diagnostics.error(DiagnosticStage.LOAD, "X", "e")
        assert not ctx2.diagnostics.has_errors()

    def test_symbol_table_assignable(self):
        from stubpy.symbols import SymbolTable
        ctx = StubContext()
        tbl = SymbolTable()
        ctx.symbol_table = tbl
        assert ctx.symbol_table is tbl

    def test_all_exports_assignable(self):
        ctx = StubContext()
        ctx.all_exports = {"Foo", "Bar"}
        assert "Foo" in ctx.all_exports

    def test_alias_lookup_unchanged(self):
        ctx = StubContext()
        ctx.alias_registry.append(AliasEntry(str | int, "types.T"))
        ctx.type_module_imports["types"] = "from pkg import types"
        assert ctx.lookup_alias(str | int) == "types.T"
        assert ctx.lookup_alias(str | float) is None
        assert "types" in ctx.used_type_imports

    def test_v01_fields_still_present(self):
        ctx = StubContext()
        assert hasattr(ctx, "alias_registry")
        assert hasattr(ctx, "type_module_imports")
        assert hasattr(ctx, "used_type_imports")

    def test_diagnostics_records_errors(self):
        ctx = StubContext()
        ctx.diagnostics.error(DiagnosticStage.EMIT, "Foo", "test error")
        assert ctx.diagnostics.has_errors()
        assert ctx.diagnostics.errors[0].symbol == "Foo"
