"""
tests/test_emitter.py
---------------------
Unit tests for stubpy.emitter:
  - insert_kw_separator
  - generate_method_stub  (property, classmethod, staticmethod, regular)
  - generate_class_stub   (annotations, methods, empty body)
  - formatting rules      (inline vs multi-line, trailing comma)
"""
from __future__ import annotations

import ast
import inspect

import pytest

from stubpy.context import StubContext
from stubpy.emitter import (
    _KW_SEP_NAME,
    _POS_SEP_NAME,
    generate_alias_stub,
    generate_class_stub,
    generate_method_stub,
    generate_overload_group_stub,
    insert_kw_separator,
    insert_pos_separator,
    methods_defined_on,
)
from stubpy.resolver import _KW_ONLY, _VAR_POS, _VAR_KW


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


def _param(name: str, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, **kw):
    return inspect.Parameter(name, kind, **kw)


# ---------------------------------------------------------------------------
# insert_kw_separator
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# methods_defined_on
# ---------------------------------------------------------------------------

class TestMethodsDefinedOn:
    def test_returns_own_methods_only(self):
        class Parent:
            def parent_method(self): pass
        class Child(Parent):
            def child_method(self): pass
        names = methods_defined_on(Child)
        assert "child_method"  in names
        assert "parent_method" not in names

    def test_public_dunders_included(self):
        class A:
            def __init__(self): pass
            def __len__(self): return 0
            def __repr__(self): return ""
        names = methods_defined_on(A)
        assert "__init__" in names
        assert "__len__"  in names
        assert "__repr__" in names

    def test_private_dunders_excluded(self):
        class A:
            def __init__(self): pass
            def __weakref__(self): pass  # internal dunder
        names = methods_defined_on(A)
        assert "__init__"    in names
        assert "__weakref__" not in names

    def test_classmethod_and_staticmethod_included(self):
        class A:
            @classmethod
            def cls_m(cls): pass
            @staticmethod
            def sta_m(): pass
        names = methods_defined_on(A)
        assert "cls_m" in names
        assert "sta_m" in names

    def test_property_included(self):
        class A:
            @property
            def val(self) -> int: return 0
        names = methods_defined_on(A)
        assert "val" in names


# ---------------------------------------------------------------------------
# generate_method_stub — regular methods
# ---------------------------------------------------------------------------

class TestGenerateMethodStubRegular:
    def test_simple_method_inline(self, ctx):
        class A:
            def move(self, x: float, y: float) -> None: pass
        stub = generate_method_stub(A, "move", ctx)
        assert "def move(self, x: float, y: float) -> None: ..." in stub

    def test_no_return_annotation(self, ctx):
        class A:
            def run(self): pass
        stub = generate_method_stub(A, "run", ctx)
        assert "def run(self)" in stub
        assert "->" not in stub

    def test_init_always_returns_none(self, ctx):
        class A:
            def __init__(self, x: int): pass
        stub = generate_method_stub(A, "__init__", ctx)
        assert "-> None" in stub

    def test_multiline_for_many_params(self, ctx):
        class A:
            def foo(self, a: int, b: str, c: float) -> None: pass
        stub = generate_method_stub(A, "foo", ctx)
        # multi-line: opening line ends with "("
        first_line = stub.splitlines()[0]
        assert first_line.rstrip().endswith("(")

    def test_trailing_comma_in_multiline(self, ctx):
        class A:
            def foo(self, a: int, b: str, c: float) -> None: pass
        stub = generate_method_stub(A, "foo", ctx)
        # The closing ) line; params lines should end with ","
        param_lines = [
            l for l in stub.splitlines()
            if l.strip() and not l.strip().startswith("def ")
            and not l.strip().startswith(")")
        ]
        for line in param_lines:
            assert line.rstrip().endswith(","), f"No trailing comma: {line!r}"

    def test_method_not_on_class_returns_empty(self, ctx):
        class A:
            pass
        stub = generate_method_stub(A, "nonexistent", ctx)
        assert stub == ""


# ---------------------------------------------------------------------------
# generate_method_stub — @property
# ---------------------------------------------------------------------------

class TestGenerateMethodStubProperty:
    def test_property_decorator_emitted(self, ctx):
        class A:
            @property
            def value(self) -> float: return 0.0
        stub = generate_method_stub(A, "value", ctx)
        assert "@property" in stub
        assert "def value(self) -> float: ..." in stub

    def test_property_with_setter(self, ctx):
        class A:
            @property
            def value(self) -> float: return self._v
            @value.setter
            def value(self, v: float) -> None: self._v = v
        stub = generate_method_stub(A, "value", ctx)
        assert "@property"      in stub
        assert "@value.setter"  in stub
        assert "def value(self, v: float) -> None: ..." in stub

    def test_property_no_return_annotation(self, ctx):
        class A:
            @property
            def name(self): return ""
        stub = generate_method_stub(A, "name", ctx)
        assert "@property" in stub
        assert "def name(self)" in stub

    def test_property_without_setter_no_setter_in_stub(self, ctx):
        class A:
            @property
            def val(self) -> int: return 0
        stub = generate_method_stub(A, "val", ctx)
        assert "@val.setter" not in stub


# ---------------------------------------------------------------------------
# generate_method_stub — @classmethod / @staticmethod
# ---------------------------------------------------------------------------

class TestGenerateMethodStubDecorated:
    def test_classmethod_decorator(self, ctx):
        class A:
            @classmethod
            def create(cls, v: int) -> "A": return cls()
        stub = generate_method_stub(A, "create", ctx)
        assert "@classmethod" in stub
        assert "def create(cls, v: int)" in stub

    def test_staticmethod_decorator(self, ctx):
        class A:
            @staticmethod
            def add(a: int, b: int) -> int: return a + b
        stub = generate_method_stub(A, "add", ctx)
        assert "@staticmethod" in stub
        assert "def add(a: int, b: int) -> int: ..." in stub

    def test_classmethod_no_self_in_sig(self, ctx):
        class A:
            @classmethod
            def make(cls) -> "A": return cls()
        stub = generate_method_stub(A, "make", ctx)
        assert "self" not in stub
        assert "cls"  in stub

    def test_staticmethod_no_self_or_cls(self, ctx):
        class A:
            @staticmethod
            def util(x: int) -> int: return x
        stub = generate_method_stub(A, "util", ctx)
        assert "self" not in stub
        assert "cls"  not in stub


# ---------------------------------------------------------------------------
# generate_class_stub
# ---------------------------------------------------------------------------

class TestGenerateClassStub:
    def test_class_line(self, ctx):
        class MyClass: pass
        stub = generate_class_stub(MyClass, ctx)
        assert stub.startswith("class MyClass:")

    def test_base_class_in_signature(self, ctx):
        class Parent: pass
        class Child(Parent): pass
        stub = generate_class_stub(Child, ctx)
        assert "class Child(Parent):" in stub

    def test_multiple_bases(self, ctx):
        class A: pass
        class B: pass
        class C(A, B): pass
        stub = generate_class_stub(C, ctx)
        assert "class C(A, B):" in stub

    def test_object_base_omitted(self, ctx):
        class A: pass
        stub = generate_class_stub(A, ctx)
        assert "object" not in stub

    def test_empty_class_gets_ellipsis(self, ctx):
        class Empty: pass
        stub = generate_class_stub(Empty, ctx)
        assert "    ..." in stub

    def test_class_level_annotations(self, ctx):
        class A:
            x: int
            y: str
        stub = generate_class_stub(A, ctx)
        assert "    x: int" in stub
        assert "    y: str" in stub

    def test_methods_indented(self, ctx):
        class A:
            def foo(self) -> None: pass
        stub = generate_class_stub(A, ctx)
        assert "    def foo(self) -> None: ..." in stub

    def test_valid_python_syntax(self, ctx):
        class A:
            def __init__(self, x: int, y: str, z: float = 1.0) -> None: pass
            def method(self) -> None: pass
        stub = generate_class_stub(A, ctx)
        try:
            ast.parse(stub)
        except SyntaxError as exc:
            pytest.fail(f"Invalid syntax in class stub: {exc}")


# ---------------------------------------------------------------------------
# Keyword-only separator in stubs
# ---------------------------------------------------------------------------

class TestKwOnlySeparatorInStub:
    def test_bare_star_emitted(self, ctx):
        class A:
            def __init__(self, a: int, *, b: str = "x") -> None: pass
        stub = generate_method_stub(A, "__init__", ctx)
        # Flatten multi-line to single line for simple check
        flat = " ".join(l.strip() for l in stub.splitlines())
        assert "*," in flat

    def test_star_before_kw_only_param(self, ctx):
        class A:
            def __init__(self, a: int, *, b: str = "x") -> None: pass
        stub = generate_method_stub(A, "__init__", ctx)
        flat = " ".join(l.strip() for l in stub.splitlines())
        assert flat.index("*,") < flat.index("b:")


# ---------------------------------------------------------------------------
# Positional-only separator
# ---------------------------------------------------------------------------

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
        # Sentinel after index 1 (b)
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
        # No positional-only params → no /
        assert "/" not in stub


class TestAliasStub:
    """generate_alias_stub emits TypeVar / TypeAlias / NewType declarations."""

    def test_typevar_simple(self, ctx):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "T = TypeVar('T')"

    def test_typevar_with_bound(self, ctx):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T', bound=int)")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "T = TypeVar('T', bound=int)"

    def test_typealias(self, ctx):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="Vector", lineno=1, kind="TypeAlias", source_str="list[float]")
        sym = AliasSymbol("Vector", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "Vector: TypeAlias = list[float]"

    def test_newtype(self, ctx):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="UserId", lineno=1, kind="NewType", source_str="NewType('UserId', int)")
        sym = AliasSymbol("UserId", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "UserId = NewType('UserId', int)"

    def test_no_ast_info_returns_empty(self, ctx):
        from stubpy.symbols import AliasSymbol
        sym = AliasSymbol("T", lineno=1, ast_info=None)
        assert generate_alias_stub(sym, ctx) == ""

    def test_paramspec(self, ctx):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="P", lineno=1, kind="ParamSpec", source_str="ParamSpec('P')")
        sym = AliasSymbol("P", lineno=1, ast_info=tv)
        result = generate_alias_stub(sym, ctx)
        assert result == "P = ParamSpec('P')"


class TestOverloadGroupStub:
    """generate_overload_group_stub emits @overload for each variant."""

    def test_two_variants_two_overloads(self, ctx):
        from stubpy.symbols import OverloadGroup, FunctionSymbol
        from stubpy.ast_pass import FunctionInfo
        fi1 = FunctionInfo("f", 1, raw_return_annotation="int",
                           raw_arg_annotations={"x": "int"})
        fi2 = FunctionInfo("f", 3, raw_return_annotation="str",
                           raw_arg_annotations={"x": "str"})
        sym1 = FunctionSymbol("f", 1, ast_info=fi1)
        sym2 = FunctionSymbol("f", 3, ast_info=fi2)
        group = OverloadGroup("f", 1, variants=[sym1, sym2])
        stub = generate_overload_group_stub(group, ctx)
        assert stub.count("@overload") == 2

    def test_empty_group_returns_empty(self, ctx):
        from stubpy.symbols import OverloadGroup
        group = OverloadGroup("f", 1, variants=[])
        assert generate_overload_group_stub(group, ctx) == ""

    def test_stub_is_valid_syntax(self, ctx):
        from stubpy.symbols import OverloadGroup, FunctionSymbol
        from stubpy.ast_pass import FunctionInfo
        fi1 = FunctionInfo("f", 1, raw_return_annotation="int",
                           raw_arg_annotations={"x": "int"})
        fi2 = FunctionInfo("f", 3, raw_return_annotation="str",
                           raw_arg_annotations={"x": "str"})
        sym1 = FunctionSymbol("f", 1, ast_info=fi1)
        sym2 = FunctionSymbol("f", 3, ast_info=fi2)
        group = OverloadGroup("f", 1, variants=[sym1, sym2])
        stub = generate_overload_group_stub(group, ctx)
        # Add dummy impl so the file is a valid module
        ast.parse(stub + "\ndef f(*a): ...")
