"""Tests for format_param."""
from __future__ import annotations

import inspect

import pytest

from stubpy.core.context import StubContext
from stubpy.emit.annotations import format_param


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


class TestFormatParam:
    def test_positional_annotated(self, ctx):
        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                               annotation=int)
        assert format_param(p, {}, ctx) == "x: int"

    def test_positional_with_default(self, ctx):
        p = inspect.Parameter("size", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                               annotation=int, default=10)
        assert format_param(p, {}, ctx) == "size: int = 10"

    def test_positional_no_annotation(self, ctx):
        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        assert format_param(p, {}, ctx) == "x"

    def test_positional_no_annotation_with_default(self, ctx):
        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                               default=5)
        assert format_param(p, {}, ctx) == "x = 5"

    def test_var_positional_no_annotation(self, ctx):
        p = inspect.Parameter("args", inspect.Parameter.VAR_POSITIONAL)
        assert format_param(p, {}, ctx) == "*args"

    def test_var_positional_with_annotation(self, ctx):
        p = inspect.Parameter("elements", inspect.Parameter.VAR_POSITIONAL,
                               annotation=str)
        assert format_param(p, {"elements": str}, ctx) == "*elements: str"

    def test_var_keyword_no_annotation(self, ctx):
        p = inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD)
        assert format_param(p, {}, ctx) == "**kwargs"

    def test_var_keyword_with_annotation(self, ctx):
        p = inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD,
                               annotation=int)
        assert format_param(p, {"kwargs": int}, ctx) == "**kwargs: int"

    def test_hints_dict_overrides_param_annotation(self, ctx):
        """hints dict (from get_type_hints) takes priority over param.annotation."""
        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                               annotation=str)
        assert format_param(p, {"x": int}, ctx) == "x: int"
