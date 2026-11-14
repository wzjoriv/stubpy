"""Tests for the # stubpy: ignore directive."""
from __future__ import annotations

from stubpy.analysis.harvest import ast_harvest


class TestIgnoreDirective:
    """Files with # stubpy: ignore are skipped by the harvester."""

    def test_ignore_directive_sets_skip_file(self):
        syms = ast_harvest("# stubpy: ignore\nclass Foo: pass\n")
        assert syms.skip_file is True
        assert syms.classes == []

    def test_ignore_case_insensitive(self):
        assert ast_harvest("# STUBPY: IGNORE\n").skip_file is True
        assert ast_harvest("# Stubpy: Ignore\n").skip_file is True

    def test_ignore_with_extra_whitespace(self):
        assert ast_harvest("#  stubpy :  ignore\n").skip_file is True

    def test_ignore_must_be_before_code(self):
        syms = ast_harvest("class Foo: pass\n# stubpy: ignore\n")
        assert syms.skip_file is False
        assert len(syms.classes) == 1

    def test_ignore_after_blank_lines(self):
        syms = ast_harvest("\n\n# stubpy: ignore\nclass Foo: pass\n")
        assert syms.skip_file is True

    def test_ignore_after_other_comments(self):
        syms = ast_harvest("# regular comment\n# stubpy: ignore\nclass Foo: pass\n")
        assert syms.skip_file is True

    def test_no_ignore_returns_false(self):
        syms = ast_harvest("class Foo: pass\n")
        assert syms.skip_file is False

    def test_empty_file_no_skip(self):
        assert ast_harvest("").skip_file is False
