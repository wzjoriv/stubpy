"""Tests for harvested RawParam lists."""
from __future__ import annotations

from stubpy.analysis.harvest import ast_harvest


class TestRawParamHarvesting:
    """FunctionInfo.raw_params is populated correctly by the AST harvester."""

    def test_simple_function_params(self):
        src = 'def f(x: int, y: str = "hi", z=3.14) -> bool: ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert len(fn.raw_params) == 3
        names = [p.name for p in fn.raw_params]
        assert names == ["x", "y", "z"]

    def test_param_annotations_captured(self):
        src = 'def f(x: int, y: str = "hi") -> bool: ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_params[0].annotation_str == "int"
        assert fn.raw_params[1].annotation_str == "str"

    def test_default_repr_captured(self):
        src = 'def f(x: int = 0, y: str = "hi"): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_params[0].default_repr == "0"
        assert fn.raw_params[1].default_repr in ('"hi"', "'hi'")

    def test_inferred_type_from_literal_default(self):
        src = 'def f(x=42, y="hello", z=True): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        inferred = {p.name: p.inferred_type_str for p in fn.raw_params}
        assert inferred["x"] == "int"
        assert inferred["y"] == "str"
        assert inferred["z"] == "bool"

    def test_param_kinds_preserved(self):
        src = 'def f(a, b=1, /, c=2, *, d=3, **kw): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        kinds = {p.name: p.kind for p in fn.raw_params}
        assert kinds["a"] == "POSITIONAL_ONLY"
        assert kinds["b"] == "POSITIONAL_ONLY"
        assert kinds["c"] == "POSITIONAL_OR_KEYWORD"
        assert kinds["d"] == "KEYWORD_ONLY"
        assert kinds["kw"] == "VAR_KEYWORD"

    def test_vararg_captured(self):
        src = 'def f(*args: str, **kwargs: int): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        kinds = {p.name: p.kind for p in fn.raw_params}
        assert kinds["args"] == "VAR_POSITIONAL"
        assert kinds["kwargs"] == "VAR_KEYWORD"
        assert fn.raw_params[0].annotation_str == "str"

    def test_variable_inferred_from_literal(self):
        src = 'X = 100\nLABEL = "hello"\nFLAG = True\nRATIO = 3.14\n'
        syms = ast_harvest(src)
        inferred = {v.name: v.inferred_type_str for v in syms.variables}
        assert inferred["X"] == "int"
        assert inferred["LABEL"] == "str"
        assert inferred["FLAG"] == "bool"
        assert inferred["RATIO"] == "float"

    def test_return_type_inferred_from_literal(self):
        src = 'def f(x):\n    return True\n'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_inferred_return == "bool"

    def test_mixed_returns_union(self):
        src = 'def f(x):\n    if x:\n        return 1\n    return "hello"\n'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_inferred_return is not None
        assert "int" in fn.raw_inferred_return
        assert "str" in fn.raw_inferred_return
