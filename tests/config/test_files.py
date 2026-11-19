"""Tests for stubpy.config.files: config discovery and loading."""
from __future__ import annotations

from pathlib import Path

import pytest

from stubpy.config import Config, find_config_file, load_config
from stubpy.config._toml import minimal_toml_parse


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
        cfg = Config.from_dict({})
        assert cfg == Config()

    def test_include_private(self):
        cfg = Config.from_dict({"include_private": True})
        assert cfg.include_private is True

    def test_verbose(self):
        cfg = Config.from_dict({"verbose": True})
        assert cfg.verbose is True

    def test_strict(self):
        cfg = Config.from_dict({"strict": True})
        assert cfg.strict is True

    def test_imports_policy(self):
        assert Config.from_dict({"imports": "stdlib", "deny-imports": ["x.*"]}).import_policy.imports == "stdlib"

    def test_removed_mode_key_is_unknown(self):
        with pytest.raises(ValueError, match="Unknown stubpy option 'mode'"):
            Config.from_dict({"mode": "ast"})

    def test_union_style_modern(self):
        cfg = Config.from_dict({"union_style": "modern"})
        assert cfg.union_style == "modern"

    def test_union_style_legacy(self):
        cfg = Config.from_dict({"union_style": "legacy"})
        assert cfg.union_style == "legacy"

    def test_union_style_invalid_raises(self):
        with pytest.raises(ValueError, match="union_style"):
            Config.from_dict({"union_style": "unknown"})

    def test_output_dir(self):
        cfg = Config.from_dict({"output_dir": "stubs"})
        assert cfg.output_dir == "stubs"

    def test_exclude_list(self):
        cfg = Config.from_dict({"exclude": ["tests/*", "setup.py"]})
        assert cfg.exclude == ("tests/*", "setup.py")

    def test_unknown_key_raises_with_suggestion(self):
        with pytest.raises(ValueError, match="did you mean 'strict'"):
            Config.from_dict({"strickt": True})

    def test_old_key_names_are_rejected(self):
        with pytest.raises(ValueError, match="execution_mode"):
            Config.from_dict({"execution_mode": "ast"})

    def test_dashed_keys(self):
        cfg = Config.from_dict({"include-private": True, "infer-types": True})
        assert cfg.include_private is True and cfg.infer_types is True

    def test_targets_and_modules(self):
        cfg = Config.from_dict({"targets": ["src/pkg"], "modules": ["pkg._core"]})
        assert cfg.targets == ("src/pkg",)
        assert cfg.modules == ("pkg._core",)


class TestLoadConfig:
    def test_no_file_gives_defaults(self, tmp_path):
        cfg = load_config(tmp_path)
        assert cfg == Config()

    def test_stubpy_toml_loaded(self, tmp_path):
        write_file(
            tmp_path,
            "stubpy.toml",
            'include_private = true\nunion_style = "legacy"\n',
        )
        cfg = load_config(tmp_path)
        assert cfg.include_private is True
        assert cfg.union_style == "legacy"

    def test_stubpy_toml_with_a_tool_table(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", '[tool.stubpy]\ninclude_private = true\nimports = "none"\n')
        cfg = load_config(tmp_path)
        assert cfg.include_private is True
        assert cfg.imports == "none"

    def test_pyproject_tool_stubpy_loaded(self, tmp_path):
        write_file(
            tmp_path,
            "pyproject.toml",
            '[tool.stubpy]\nstrict = true\n',
        )
        cfg = load_config(tmp_path)
        assert cfg.strict is True

    def test_imports_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'imports = "none"\n')
        cfg = load_config(tmp_path)
        assert cfg.imports == "none"

    def test_output_dir_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'output_dir = "stubs"\n')
        cfg = load_config(tmp_path)
        assert cfg.output_dir == str(tmp_path / "stubs")

    def test_exclude_in_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'exclude = ["tests/*"]\n')
        cfg = load_config(tmp_path)
        assert cfg.exclude == ("tests/*",)


class TestTypeAliasStyleConfig:
    """alias_style key is parsed correctly from config files."""

    def test_compatible_value(self):
        cfg = Config.from_dict({"alias_style": "compatible"})
        assert cfg.alias_style == "compatible"

    def test_pep695_value(self):
        cfg = Config.from_dict({"alias_style": "pep695"})
        assert cfg.alias_style == "pep695"

    def test_auto_value(self):
        cfg = Config.from_dict({"alias_style": "auto"})
        assert cfg.alias_style == "auto"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="alias_style"):
            Config.from_dict({"alias_style": "unknown"})

    def test_default_is_compatible(self):
        assert Config().alias_style == "compatible"

    def test_load_from_file(self, tmp_path):
        (tmp_path / "stubpy.toml").write_text(
            'alias_style = "pep695"\n', encoding="utf-8"
        )
        cfg = load_config(tmp_path)
        assert cfg.alias_style == "pep695"


class TestResolveFlags:
    """TOML and default values for resolve_kwargs / resolve_args."""

    def test_resolve_kwargs_default_true(self):
        from stubpy.config import Config
        assert Config().resolve_kwargs is True

    def test_resolve_args_default_true(self):
        from stubpy.config import Config
        assert Config().resolve_args is True

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


class TestTargetsAndModules:
    """The ``targets`` / ``modules`` keys and path resolution against the config file."""

    def test_targets_resolved_against_config_folder(self, tmp_path):
        write_file(tmp_path, "pyproject.toml", '[tool.stubpy]\ntargets = ["src/pkg", "tools/*.py"]\n')
        nested = tmp_path / "src" / "pkg"
        nested.mkdir(parents=True)
        cfg = load_config(nested)
        assert cfg.targets == (str(tmp_path / "src/pkg"), str(tmp_path / "tools/*.py"))

    def test_absolute_target_kept(self, tmp_path):
        absolute = (tmp_path / "elsewhere").as_posix()
        write_file(tmp_path, "stubpy.toml", f'targets = ["{absolute}"]\n')
        assert load_config(tmp_path).targets == (absolute,)

    def test_modules_are_not_paths(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'modules = ["pkg._core", "pkg.fast"]\n')
        assert load_config(tmp_path).modules == ("pkg._core", "pkg.fast")

    def test_single_string_target(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'targets = "src"\n')
        assert load_config(tmp_path).targets == (str(tmp_path / "src"),)

    def test_invalid_file_names_the_file(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", 'union_style = "fast"\n')
        with pytest.raises(ValueError, match="stubpy.toml"):
            load_config(tmp_path)

    def test_default_start_is_working_folder(self, tmp_path, monkeypatch):
        write_file(tmp_path, "stubpy.toml", "strict = true\n")
        monkeypatch.chdir(tmp_path)
        assert load_config().strict is True

    def test_file_path_start(self, tmp_path):
        write_file(tmp_path, "stubpy.toml", "strict = true\n")
        src = write_file(tmp_path, "mod.py", "")
        assert load_config(src).strict is True


class TestMinimalToml:
    """The fallback parser used on Python 3.10 without tomli."""

    def test_multiline_array_with_comments(self):
        text = '[tool.stubpy]\ntargets = [\n  "src/a",  # first\n  "b",\n]\nunion_style = "legacy"  # note\n'
        assert minimal_toml_parse(text) == {"tool": {"stubpy": {"targets": ["src/a", "b"], "union_style": "legacy"}}}

    def test_dashed_key(self):
        assert minimal_toml_parse("include-private = true\n") == {"include-private": True}
