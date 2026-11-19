"""Tests for stubpy.config.options: Config."""
from __future__ import annotations

from stubpy.config import Config


class TestImportPolicyFields:
    def test_default_imports(self):
        assert Config().imports == "all" and Config().may_import

    def test_mode_is_gone(self):
        import pytest
        with pytest.raises(TypeError):
            Config(mode="ast")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            Config(import_modules=False)  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown stubpy option 'mode'"):
            Config.from_dict({"mode": "ast"})


class TestConfig:
    def test_defaults(self):
        cfg = Config()
        assert cfg.imports == "all"
        assert cfg.include_private is False
        assert cfg.respect_all     is True
        assert cfg.verbose         is False
        assert cfg.strict          is False

    def test_custom(self):
        cfg = Config(
            imports="none",
            include_private=True,
            respect_all=False,
            verbose=True,
            strict=True,
        )
        assert cfg.imports == "none"
        assert cfg.include_private is True
        assert cfg.respect_all     is False
        assert cfg.verbose         is True
        assert cfg.strict          is True

    def test_imports_values(self):
        import pytest
        assert Config(imports=["pkg", "other.*"]).imports == ("pkg", "other.*")
        assert Config(imports="STDLIB").imports == "stdlib"
        with pytest.raises(ValueError, match="'all', 'none', 'stdlib'"):
            Config(imports="some")
        with pytest.raises(TypeError, match="deny_imports"):
            Config(deny_imports=["not valid"])


class TestConfigResolveFlags:
    """Config.resolve_kwargs and resolve_args fields."""

    def test_defaults_are_true(self):
        from stubpy.config import Config
        cfg = Config()
        assert cfg.resolve_kwargs is True
        assert cfg.resolve_args is True

    def test_can_set_false(self):
        from stubpy.config import Config
        cfg = Config(resolve_kwargs=False, resolve_args=False)
        assert cfg.resolve_kwargs is False
        assert cfg.resolve_args is False

    def test_partial_override(self):
        from stubpy.config import Config
        cfg = Config(resolve_kwargs=False)
        assert cfg.resolve_kwargs is False
        assert cfg.resolve_args is True


class TestValidation:
    """__post_init__ coerces strings to enums and rejects bad values with clear messages."""

    def test_strings_become_enums(self):
        from stubpy.config import AliasStyle, UnionStyle
        cfg = Config(union_style="LEGACY", alias_style="pep695")
        assert cfg.union_style is UnionStyle.LEGACY
        assert cfg.alias_style is AliasStyle.PEP695

    def test_enums_compare_equal_to_their_values(self):
        assert Config().union_style == "modern"
        assert str(Config(alias_style="auto").alias_style) == "auto"

    def test_bad_choice_lists_choices(self):
        import pytest
        with pytest.raises(ValueError, match="'emit', 'resolve'"):
            Config(version_branches="both")

    def test_bad_style(self):
        import pytest
        with pytest.raises(ValueError, match="union_style"):
            Config(union_style="pep604")

    def test_flag_must_be_bool(self):
        import pytest
        with pytest.raises(TypeError, match="include_private must be a bool"):
            Config(include_private="yes")

    def test_list_fields_become_tuples(self):
        from pathlib import Path
        cfg = Config(exclude=["a/*"], targets=[Path("src")], modules="pkg.core")
        assert cfg.exclude == ("a/*",)
        assert cfg.targets == (str(Path("src")),)
        assert cfg.modules == ("pkg.core",)

    def test_list_items_must_be_strings(self):
        import pytest
        with pytest.raises(TypeError, match="exclude must contain strings"):
            Config(exclude=[1])

    def test_frozen(self):
        import dataclasses

        import pytest
        with pytest.raises(dataclasses.FrozenInstanceError):
            Config().strict = True  # type: ignore[misc]


class TestReplaceAndFromDict:
    def test_replace_returns_new_validated_copy(self):
        import pytest
        base = Config()
        changed = base.replace(include_private=True)
        assert changed.include_private is True and changed.imports == "all"
        assert base.include_private is False
        with pytest.raises(ValueError):
            base.replace(alias_style="nope")

    def test_from_dict_round_trip(self):
        import dataclasses
        cfg = Config(imports="none", exclude=["x"], output_dir="stubs", strict=True)
        assert Config.from_dict(dataclasses.asdict(cfg)) == cfg
