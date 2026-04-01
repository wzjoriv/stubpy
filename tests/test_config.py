"""
tests/test_config.py
--------------------
Unit tests for stubpy.config:
  - find_config_file (upward search for stubby.toml / pyproject.toml)
  - load_config (reads file, builds StubConfig)
  - _minimal_toml_parse (fallback parser for Python 3.10)
  - _build_config (maps raw TOML dict to StubConfig)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stubpy.config import (
    _build_config,
    _minimal_toml_parse,
    find_config_file,
    load_config,
)
from stubpy.context import ExecutionMode, StubConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_file(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# find_config_file
# ---------------------------------------------------------------------------

class TestFindConfigFile:
    def test_finds_stubpy_toml(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", "[tool.stubpy]\n")
        assert find_config_file(tmp_path) == tmp_path / "stubpy.toml"

    def test_finds_pyproject_with_tool_stubpy(self, tmp_path):
        write_file(tmp_path, "pyproject.toml", "[tool.stubpy]\ninclude_private = true\n")
        assert find_config_file(tmp_path) == tmp_path / "pyproject.toml"

    def test_prefers_stubpy_toml_over_pyproject(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", "")
        write_file(tmp_path, "pyproject.toml", "[tool.stubpy]\n")
        assert find_config_file(tmp_path) == tmp_path / "stubpy.toml"

    def test_returns_none_when_no_config(self, tmp_path):
        assert find_config_file(tmp_path) is None

    def test_pyproject_without_tool_stubpy_ignored(self, tmp_path):
        write_file(tmp_path, "pyproject.toml", "[tool.black]\nline-length = 88\n")
        assert find_config_file(tmp_path) is None

    def test_walks_upward(self, tmp_path):
        # Config in parent; search from child
        write_file(tmp_path, "stubpy.toml", "")
        child = tmp_path / "src" / "mypackage"
        child.mkdir(parents=True)
        result = find_config_file(child)
        assert result == tmp_path / "stubpy.toml"

    def test_stops_at_filesystem_root(self, tmp_path):
        # No config anywhere — should not raise
        result = find_config_file(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# _minimal_toml_parse
# ---------------------------------------------------------------------------

class TestMinimalTomlParse:
    def test_simple_string(self):
        r = _minimal_toml_parse('key = "value"\n')
        assert r["key"] == "value"

    def test_single_quoted_string(self):
        r = _minimal_toml_parse("key = 'value'\n")
        assert r["key"] == "value"

    def test_bool_true(self):
        r = _minimal_toml_parse("flag = true\n")
        assert r["flag"] is True

    def test_bool_false(self):
        r = _minimal_toml_parse("flag = false\n")
        assert r["flag"] is False

    def test_section_header(self):
        r = _minimal_toml_parse("[tool.stubpy]\ninclude_private = true\n")
        assert r["tool"]["stubpy"]["include_private"] is True

    def test_string_array(self):
        r = _minimal_toml_parse('exclude = ["*.py", "tests/*"]\n')
        assert r["exclude"] == ["*.py", "tests/*"]

    def test_ignores_comments(self):
        r = _minimal_toml_parse("# comment\nkey = \"val\"\n")
        assert r["key"] == "val"
        assert "comment" not in r

    def test_ignores_unknown_value_types(self):
        # Integer values are not supported by the minimal parser — silently skipped
        r = _minimal_toml_parse("port = 8080\n")
        assert "port" not in r  # not supported → skipped

    def test_empty_input(self):
        assert _minimal_toml_parse("") == {}


# ---------------------------------------------------------------------------
# _build_config
# ---------------------------------------------------------------------------

class TestBuildConfig:
    def test_empty_dict_gives_defaults(self):
        cfg = _build_config({})
        assert cfg == StubConfig()

    def test_include_private(self):
        cfg = _build_config({"include_private": True})
        assert cfg.include_private is True

    def test_verbose(self):
        cfg = _build_config({"verbose": True})
        assert cfg.verbose is True

    def test_strict(self):
        cfg = _build_config({"strict": True})
        assert cfg.strict is True

    def test_execution_mode_runtime(self):
        cfg = _build_config({"execution_mode": "runtime"})
        assert cfg.execution_mode == ExecutionMode.RUNTIME

    def test_execution_mode_ast_only(self):
        cfg = _build_config({"execution_mode": "ast_only"})
        assert cfg.execution_mode == ExecutionMode.AST_ONLY

    def test_execution_mode_auto(self):
        cfg = _build_config({"execution_mode": "auto"})
        assert cfg.execution_mode == ExecutionMode.AUTO

    def test_execution_mode_invalid_ignored(self):
        cfg = _build_config({"execution_mode": "unknown"})
        assert cfg.execution_mode == ExecutionMode.RUNTIME  # unchanged default

    def test_typing_style_modern(self):
        cfg = _build_config({"typing_style": "modern"})
        assert cfg.typing_style == "modern"

    def test_typing_style_legacy(self):
        cfg = _build_config({"typing_style": "legacy"})
        assert cfg.typing_style == "legacy"

    def test_typing_style_invalid_ignored(self):
        cfg = _build_config({"typing_style": "unknown"})
        assert cfg.typing_style == "modern"  # unchanged default

    def test_output_dir(self):
        cfg = _build_config({"output_dir": "stubs"})
        assert cfg.output_dir == "stubs"

    def test_exclude_list(self):
        cfg = _build_config({"exclude": ["tests/*", "setup.py"]})
        assert cfg.exclude == ["tests/*", "setup.py"]

    def test_unknown_keys_ignored(self):
        cfg = _build_config({"future_key": "value", "strict": True})
        assert cfg.strict is True  # known key applied
        assert cfg == StubConfig(strict=True)  # unknown key ignored


# ---------------------------------------------------------------------------
# load_config (end-to-end)
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_no_file_gives_defaults(self, tmp_path):
        cfg = load_config(tmp_path)
        assert cfg == StubConfig()

    def test_stubpy_toml_loaded(self, tmp_path):
        write_file(
            tmp_path,
            "stubpy.toml",
            'include_private = true\ntyping_style = "legacy"\n',
        )
        cfg = load_config(tmp_path)
        assert cfg.include_private is True
        assert cfg.typing_style == "legacy"

    def test_pyproject_tool_stubpy_loaded(self, tmp_path):
        write_file(
            tmp_path,
            "pyproject.toml",
            '[tool.stubpy]\nstrict = true\n',
        )
        cfg = load_config(tmp_path)
        assert cfg.strict is True

    def test_execution_mode_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'execution_mode = "ast_only"\n')
        cfg = load_config(tmp_path)
        assert cfg.execution_mode == ExecutionMode.AST_ONLY

    def test_output_dir_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'output_dir = "stubs"\n')
        cfg = load_config(tmp_path)
        assert cfg.output_dir == "stubs"

    def test_exclude_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'exclude = ["tests/*"]\n')
        cfg = load_config(tmp_path)
        assert cfg.exclude == ["tests/*"]
