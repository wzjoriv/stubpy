"""Tests for stubpy.config.files: config discovery and loading."""
from __future__ import annotations

from pathlib import Path

from stubpy.config import ExecutionMode, StubConfig, find_config_file, load_config
from stubpy.config.files import config_from_dict


def write_file(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


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
        write_file(tmp_path, "stubpy.toml", "")
        child = tmp_path / "src" / "mypackage"
        child.mkdir(parents=True)
        result = find_config_file(child)
        assert result == tmp_path / "stubpy.toml"

    def test_stops_at_filesystem_root(self, tmp_path):
        result = find_config_file(tmp_path)
        assert result is None


class TestBuildConfig:
    def test_empty_dict_gives_defaults(self):
        cfg = config_from_dict({})
        assert cfg == StubConfig()

    def test_include_private(self):
        cfg = config_from_dict({"include_private": True})
        assert cfg.include_private is True

    def test_verbose(self):
        cfg = config_from_dict({"verbose": True})
        assert cfg.verbose is True

    def test_strict(self):
        cfg = config_from_dict({"strict": True})
        assert cfg.strict is True

    def test_execution_mode_runtime(self):
        cfg = config_from_dict({"execution_mode": "runtime"})
        assert cfg.execution_mode == ExecutionMode.RUNTIME

    def test_execution_mode_ast_only(self):
        cfg = config_from_dict({"execution_mode": "ast_only"})
        assert cfg.execution_mode == ExecutionMode.AST_ONLY

    def test_execution_mode_auto(self):
        cfg = config_from_dict({"execution_mode": "auto"})
        assert cfg.execution_mode == ExecutionMode.AUTO

    def test_execution_mode_invalid_ignored(self):
        cfg = config_from_dict({"execution_mode": "unknown"})
        assert cfg.execution_mode == ExecutionMode.RUNTIME

    def test_union_style_modern(self):
        cfg = config_from_dict({"union_style": "modern"})
        assert cfg.union_style == "modern"

    def test_union_style_legacy(self):
        cfg = config_from_dict({"union_style": "legacy"})
        assert cfg.union_style == "legacy"

    def test_union_style_invalid_ignored(self):
        cfg = config_from_dict({"union_style": "unknown"})
        assert cfg.union_style == "modern"

    def test_output_dir(self):
        cfg = config_from_dict({"output_dir": "stubs"})
        assert cfg.output_dir == "stubs"

    def test_exclude_list(self):
        cfg = config_from_dict({"exclude": ["tests/*", "setup.py"]})
        assert cfg.exclude == ["tests/*", "setup.py"]

    def test_unknown_keys_ignored(self):
        cfg = config_from_dict({"future_key": "value", "strict": True})
        assert cfg.strict is True
        assert cfg == StubConfig(strict=True)


class TestLoadConfig:
    def test_no_file_gives_defaults(self, tmp_path):
        cfg = load_config(tmp_path)
        assert cfg == StubConfig()

    def test_stubpy_toml_loaded(self, tmp_path):
        write_file(
            tmp_path,
            "stubpy.toml",
            'include_private = true\nunion_style = "legacy"\n',
        )
        cfg = load_config(tmp_path)
        assert cfg.include_private is True
        assert cfg.union_style == "legacy"

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


class TestTypeAliasStyleConfig:
    """alias_style key is parsed correctly from config files."""

    def test_compatible_value(self):
        cfg = config_from_dict({"alias_style": "compatible"})
        assert cfg.alias_style == "compatible"

    def test_pep695_value(self):
        cfg = config_from_dict({"alias_style": "pep695"})
        assert cfg.alias_style == "pep695"

    def test_auto_value(self):
        cfg = config_from_dict({"alias_style": "auto"})
        assert cfg.alias_style == "auto"

    def test_invalid_value_ignored(self):
        cfg = config_from_dict({"alias_style": "unknown"})
        assert cfg.alias_style == "compatible"

    def test_default_is_compatible(self):
        assert StubConfig().alias_style == "compatible"

    def test_load_from_file(self, tmp_path):
        (tmp_path / "stubpy.toml").write_text(
            'alias_style = "pep695"\n', encoding="utf-8"
        )
        cfg = load_config(tmp_path)
        assert cfg.alias_style == "pep695"


class TestResolveFlags:
    """TOML and default values for resolve_kwargs / resolve_args."""

    def test_resolve_kwargs_default_true(self):
        from stubpy.config import StubConfig
        assert StubConfig().resolve_kwargs is True

    def test_resolve_args_default_true(self):
        from stubpy.config import StubConfig
        assert StubConfig().resolve_args is True

    def test_resolve_kwargs_false_from_toml(self, tmp_path):
        from stubpy.config import load_config
        (tmp_path / "stubpy.toml").write_text("resolve_kwargs = false\n")
        cfg = load_config(tmp_path)
        assert cfg.resolve_kwargs is False

    def test_resolve_args_false_from_toml(self, tmp_path):
        from stubpy.config import load_config
        (tmp_path / "stubpy.toml").write_text("resolve_args = false\n")
        cfg = load_config(tmp_path)
        assert cfg.resolve_args is False

    def test_both_false_from_toml(self, tmp_path):
        from stubpy.config import load_config
        (tmp_path / "stubpy.toml").write_text(
            "resolve_kwargs = false\nresolve_args = false\n"
        )
        cfg = load_config(tmp_path)
        assert cfg.resolve_kwargs is False
        assert cfg.resolve_args is False

    def test_resolve_flags_default_not_overridden_by_missing_key(self, tmp_path):
        from stubpy.config import load_config
        (tmp_path / "stubpy.toml").write_text("verbose = true\n")
        cfg = load_config(tmp_path)
        assert cfg.resolve_kwargs is True
        assert cfg.resolve_args is True
