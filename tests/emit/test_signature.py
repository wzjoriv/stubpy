"""Tests for the / and * separators in signatures."""
from __future__ import annotations

import inspect

from stubpy.emit import (
    generate_method_stub,
    insert_kw_separator,
    insert_pos_separator,
)
from tests.conftest import (
    _KW_ONLY,
    _KW_SEP_NAME,
    _POS_SEP_NAME,
    _VAR_POS,
    _param,
)


class TestInsertKwSeparator:
    def test_no_kw_only_unchanged(self, ctx):
        params = [
            (_param("x", annotation=int), {}),
            (_param("y", annotation=str), {}),
        ]
        result = insert_kw_separator(params)
        assert len(result) == len(params)

    def test_sentinel_inserted_before_first_kw_only(self):
        params = [
            (_param("a", annotation=int), {}),
            (_param("b", kind=_KW_ONLY, annotation=str), {}),
        ]
        result = insert_kw_separator(params)
        sep_idx = next(i for i, (p, _) in enumerate(result) if p.name == _KW_SEP_NAME)
        b_idx   = next(i for i, (p, _) in enumerate(result) if p.name == "b")
        assert sep_idx < b_idx

    def test_no_sentinel_when_var_pos_present(self):
        """*args already acts as separator; no bare * needed."""
        params = [
            (_param("args", kind=_VAR_POS), {}),
            (_param("b", kind=_KW_ONLY, annotation=str), {}),
        ]
        result = insert_kw_separator(params)
        names = [p.name for p, _ in result]
        assert _KW_SEP_NAME not in names

    def test_multiple_kw_only_only_one_sentinel(self):
        params = [
            (_param("a", annotation=int), {}),
            (_param("b", kind=_KW_ONLY, annotation=str), {}),
            (_param("c", kind=_KW_ONLY, annotation=float), {}),
        ]
        result = insert_kw_separator(params)
        sentinels = [p for p, _ in result if p.name == _KW_SEP_NAME]
        assert len(sentinels) == 1


class TestKwOnlySeparatorInStub:
    def test_bare_star_emitted(self, ctx):
        class A:
            def __init__(self, a: int, *, b: str = "x") -> None: pass
        stub = generate_method_stub(A, "__init__", ctx)
        flat = " ".join(l.strip() for l in stub.splitlines())
        assert "*," in flat

    def test_star_before_kw_only_param(self, ctx):
        class A:
            def __init__(self, a: int, *, b: str = "x") -> None: pass
        stub = generate_method_stub(A, "__init__", ctx)
        flat = " ".join(l.strip() for l in stub.splitlines())
        assert flat.index("*,") < flat.index("b:")


class TestInsertPosSeparator:
    """insert_pos_separator inserts '/' sentinel after last POSITIONAL_ONLY param."""

    def test_no_pos_only_unchanged(self):
        a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        result = insert_pos_separator([(a, {})])
        assert len(result) == 1

    def test_single_pos_only_gets_sentinel(self):
        a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
        b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        result = insert_pos_separator([(a, {}), (b, {})])
        assert len(result) == 3
        assert result[1][0].name == _POS_SEP_NAME

    def test_multiple_pos_only_sentinel_after_last(self):
        a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
        b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_ONLY)
        c = inspect.Parameter("c", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        result = insert_pos_separator([(a, {}), (b, {}), (c, {})])
        assert result[2][0].name == _POS_SEP_NAME
        assert result[3][0].name == "c"

    def test_all_pos_only_sentinel_at_end(self):
        a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
        b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_ONLY)
        result = insert_pos_separator([(a, {}), (b, {})])
        assert result[-1][0].name == _POS_SEP_NAME


class TestPositionalOnlyInMethodStub:
    """The / separator is correctly emitted in method and function stubs."""

    def test_slash_emitted_for_pos_only_method(self, ctx):
        class MyClass:
            def method(self, x: int, y: int, /, z: int = 0) -> int:
                return x + y + z

        stub = generate_method_stub(MyClass, "method", ctx)
        flat = " ".join(line.strip() for line in stub.splitlines())
        assert "/" in flat

    def test_slash_before_regular_param(self, ctx):
        class MyClass:
            def method(self, a: int, /, b: int) -> int:
                return a + b

        stub = generate_method_stub(MyClass, "method", ctx)
        flat = " ".join(line.strip() for line in stub.splitlines())
        slash_pos = flat.index("/")
        b_pos = flat.index("b:")
        assert slash_pos < b_pos

    def test_slash_and_star_together(self, ctx):
        class MyClass:
            def method(self, a: int, /, b: int, *, c: int) -> int:
                return a + b + c

        stub = generate_method_stub(MyClass, "method", ctx)
        flat = " ".join(line.strip() for line in stub.splitlines())
        assert "/" in flat
        assert "*," in flat
        assert flat.index("/") < flat.index("*,")

    def test_no_slash_without_pos_only(self, ctx):
        class MyClass:
            def method(self, a: int, b: int) -> int:
                return a + b

        stub = generate_method_stub(MyClass, "method", ctx)
        assert "/" not in stub
