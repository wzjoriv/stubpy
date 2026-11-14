"""Tests for stubpy.config.options: StubConfig and ExecutionMode."""
from __future__ import annotations

from stubpy.config import ExecutionMode, StubConfig


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


class TestStubConfigResolveFlags:
    """StubConfig.resolve_kwargs and resolve_args fields."""

    def test_defaults_are_true(self):
        from stubpy.config import StubConfig
        cfg = StubConfig()
        assert cfg.resolve_kwargs is True
        assert cfg.resolve_args is True

    def test_can_set_false(self):
        from stubpy.config import StubConfig
        cfg = StubConfig(resolve_kwargs=False, resolve_args=False)
        assert cfg.resolve_kwargs is False
        assert cfg.resolve_args is False

    def test_partial_override(self):
        from stubpy.config import StubConfig
        cfg = StubConfig(resolve_kwargs=False)
        assert cfg.resolve_kwargs is False
        assert cfg.resolve_args is True
