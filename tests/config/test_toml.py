"""Tests for the minimal TOML fallback parser."""
from __future__ import annotations

from stubpy.config._toml import minimal_toml_parse


class TestMinimalTomlParse:
    def test_simple_string(self):
        r = minimal_toml_parse('key = "value"\n')
        assert r["key"] == "value"

    def test_single_quoted_string(self):
        r = minimal_toml_parse("key = 'value'\n")
        assert r["key"] == "value"

    def test_bool_true(self):
        r = minimal_toml_parse("flag = true\n")
        assert r["flag"] is True

    def test_bool_false(self):
        r = minimal_toml_parse("flag = false\n")
        assert r["flag"] is False

    def test_section_header(self):
        r = minimal_toml_parse("[tool.stubpy]\ninclude_private = true\n")
        assert r["tool"]["stubpy"]["include_private"] is True

    def test_string_array(self):
        r = minimal_toml_parse('exclude = ["*.py", "tests/*"]\n')
        assert r["exclude"] == ["*.py", "tests/*"]

    def test_ignores_comments(self):
        r = minimal_toml_parse("# comment\nkey = \"val\"\n")
        assert r["key"] == "val"
        assert "comment" not in r

    def test_ignores_unknown_value_types(self):
        r = minimal_toml_parse("port = 8080\n")
        assert "port" not in r

    def test_empty_input(self):
        assert minimal_toml_parse("") == {}
