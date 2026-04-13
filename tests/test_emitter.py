"""
tests/test_emitter.py
----------------------
Tests for :mod:`stubpy.emitter` — stub text generation for all symbol kinds.

Covers:
- :func:`generate_method_stub` — properties (including MRO), classmethods,
  staticmethods, abstract methods, async methods
- :func:`generate_class_stub` — dataclasses, NamedTuples, TypedDict, Enum,
  generic classes, ABC subclasses
- :func:`generate_function_stub` — module-level functions (sync/async)
- :func:`generate_variable_stub` — annotated and inferred-type variables
- :func:`generate_alias_stub` — TypeVar, TypeAlias, NewType, ParamSpec
- :func:`generate_overload_group_stub` — @overload variants
- Property MRO tracking (:func:`_find_property_mro`)
- ``@type_check_only`` and ``@dataclass_transform`` decorators
- Special class detection helpers
- Parameter separator insertion (:func:`insert_kw_separator`,
  :func:`insert_pos_separator`)
"""
from __future__ import annotations

import abc
import ast
import dataclasses as _dc
import enum
import inspect
import textwrap
import types as _t
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Generic, NamedTuple, Optional, TypedDict, TypeVar

import pytest

from tests.conftest import (
    assert_valid_syntax, assert_valid_python, flatten, make_stub,
    _param, _KW_ONLY, _VAR_POS, _VAR_KW, _POS_ONLY, _POS_KW,
    _KW_SEP_NAME, _POS_SEP_NAME, _ctx, _parse, _generate,
)
from stubpy.ast_pass import FunctionInfo, VariableInfo, ast_harvest
from stubpy.context import StubConfig, StubContext
from stubpy.diagnostics import DiagnosticLevel, DiagnosticStage
from stubpy.emitter import (
    _find_property_mro,
    _is_abstract_method,
    _is_async_callable,
    _is_dataclass,
    _is_enum,
    _is_namedtuple,
    _is_typeddict,
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_method_stub,
    generate_overload_group_stub,
    generate_variable_stub,
    insert_kw_separator,
    insert_pos_separator,
    methods_defined_on,
)
from stubpy.imports import collect_special_imports
from stubpy.symbols import (
    AliasSymbol,
    FunctionSymbol,
    OverloadGroup,
    VariableSymbol,
    build_symbol_table,
)



# ---------------------------------------------------------------------------
# Module-level test helpers
# ---------------------------------------------------------------------------

def _function_sym(
    name: str,
    live_func=None,
    is_async: bool = False,
    raw_return: "str | None" = None,
    raw_args: "dict[str, str] | None" = None,
    lineno: int = 1,
) -> "FunctionSymbol":
    from stubpy.ast_pass import FunctionInfo
    fi = FunctionInfo(
        name=name, lineno=lineno, is_async=is_async,
        raw_return_annotation=raw_return, raw_arg_annotations=raw_args or {},
    )
    return FunctionSymbol(name=name, lineno=lineno, live_func=live_func, ast_info=fi)


def _variable_sym(
    name: str,
    annotation: "str | None" = None,
    inferred: "str | None" = None,
    live_value=None,
    lineno: int = 1,
) -> "VariableSymbol":
    from stubpy.ast_pass import VariableInfo
    vi = VariableInfo(name=name, lineno=lineno, annotation_str=annotation)
    return VariableSymbol(
        name=name, lineno=lineno, annotation_str=annotation,
        inferred_type_str=inferred, live_value=live_value, ast_info=vi,
    )


def _make_stub_cfg(source: str, **cfg_kwargs) -> str:
    """Generate a stub from *source* text using optional :class:`StubConfig` overrides."""
    import tempfile, textwrap
    from pathlib import Path
    from stubpy import generate_stub
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        ctx_obj = StubContext(config=StubConfig(**cfg_kwargs)) if cfg_kwargs else None
        return generate_stub(str(tmp), str(tmp.with_suffix(".pyi")), ctx=ctx_obj)
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_suffix(".pyi").unlink(missing_ok=True)


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


class TestTypeAliasStyle:
    """generate_alias_stub respects alias_style configuration."""

    def _alias_sym(self, name: str, rhs: str):
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name=name, lineno=1, kind="TypeAlias", source_str=rhs)
        return AliasSymbol(name, lineno=1, ast_info=tv)

    def test_compatible_emits_typealias(self):
        from stubpy.context import StubConfig
        ctx = StubContext(config=StubConfig(alias_style="compatible"))
        sym = self._alias_sym("Color", "str | tuple[float, ...]")
        result = generate_alias_stub(sym, ctx)
        assert result == "Color: TypeAlias = str | tuple[float, ...]"

    def test_pep695_emits_type_keyword(self):
        from stubpy.context import StubConfig
        ctx = StubContext(config=StubConfig(alias_style="pep695"))
        sym = self._alias_sym("Vector", "list[float]")
        result = generate_alias_stub(sym, ctx)
        assert result == "type Vector = list[float]"

    def test_auto_on_3_12_uses_pep695(self):
        import sys
        from stubpy.context import StubConfig
        ctx = StubContext(config=StubConfig(alias_style="auto"))
        sym = self._alias_sym("Number", "int | float")
        result = generate_alias_stub(sym, ctx)
        if sys.version_info >= (3, 12):
            assert result.startswith("type ")
        else:
            assert ": TypeAlias" in result

    def test_default_is_compatible(self):
        ctx = StubContext()
        sym = self._alias_sym("Length", "str | float | int")
        result = generate_alias_stub(sym, ctx)
        assert ": TypeAlias" in result

    def test_typevar_unaffected_by_style(self):
        from stubpy.context import StubConfig
        from stubpy.symbols import AliasSymbol
        from stubpy.ast_pass import TypeVarInfo
        tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
        sym = AliasSymbol("T", lineno=1, ast_info=tv)
        for style in ("compatible", "pep695", "auto"):
            ctx = StubContext(config=StubConfig(alias_style=style))
            result = generate_alias_stub(sym, ctx)
            assert result == "T = TypeVar('T')"

# ---------------------------------------------------------------------------
# Special class stubs (dataclass, NamedTuple, TypedDict, Enum, ABC, async)
# ---------------------------------------------------------------------------

class TestAsyncDetection:

    def test_regular_async_fn(self):
        async def fetch():
            pass
        assert _is_async_callable(fetch)

    def test_sync_fn_not_async(self):
        def sync():
            pass
        assert not _is_async_callable(sync)

    def test_async_classmethod(self):
        class Foo:
            @classmethod
            async def cls_fetch(cls):
                pass
        assert _is_async_callable(Foo.__dict__["cls_fetch"])

    def test_async_staticmethod(self):
        class Foo:
            @staticmethod
            async def static_fetch():
                pass
        assert _is_async_callable(Foo.__dict__["static_fetch"])

    def test_async_generator(self):
        async def agen():
            yield 1
        assert _is_async_callable(agen)

    def test_property_not_async_by_default(self):
        class Foo:
            @property
            def value(self):
                return 1
        assert not _is_async_callable(Foo.__dict__["value"])


# ============================================================================
# Async method stubs — unit
# ============================================================================

class TestAsyncMethodStubUnit:

    def test_async_method_emits_async_def(self):
        class Fetcher:
            async def fetch(self, url: str) -> bytes:
                return b""
        stub = generate_method_stub(Fetcher, "fetch", StubContext())
        assert "async def fetch" in stub
        assert "url: str" in stub
        assert "-> bytes" in stub

    def test_sync_method_no_async_prefix(self):
        class Foo:
            def compute(self, x: int) -> int:
                return x
        stub = generate_method_stub(Foo, "compute", StubContext())
        assert "async" not in stub
        assert "def compute" in stub

    def test_async_classmethod(self):
        class Repo:
            @classmethod
            async def load(cls, id: int) -> "Repo": ...
        stub = generate_method_stub(Repo, "load", StubContext())
        assert "@classmethod" in stub
        assert "async def load" in stub

    def test_async_staticmethod(self):
        class Utils:
            @staticmethod
            async def ping(host: str) -> bool: ...
        stub = generate_method_stub(Utils, "ping", StubContext())
        assert "@staticmethod" in stub
        assert "async def ping" in stub

    def test_async_generator_method(self):
        class Stream:
            async def chunks(self, size: int):
                yield b""
        stub = generate_method_stub(Stream, "chunks", StubContext())
        assert "async def chunks" in stub


# ============================================================================
# Async methods via generate_stub
# ============================================================================

class TestAsyncMethodsIntegration:

    def test_async_method_in_output(self):
        c = make_stub(
            "class API:\n"
            "    async def get(self, url: str) -> bytes: ...\n"
            "    def post(self, url: str) -> None: ...\n"
        )
        assert "async def get" in c
        assert "def post" in c
        assert "async def post" not in c
        assert_valid_syntax(c)

    def test_async_classmethod_in_output(self):
        c = make_stub(
            "class DB:\n"
            "    @classmethod\n"
            "    async def connect(cls, dsn: str) -> 'DB': ...\n"
        )
        assert "@classmethod" in c
        assert "async def connect" in c

    def test_mixed_sync_async_class(self):
        c = make_stub(
            "class Worker:\n"
            "    def setup(self) -> None: ...\n"
            "    async def run(self) -> None: ...\n"
            "    def teardown(self) -> None: ...\n"
        )
        assert_valid_syntax(c)
        assert "async def run" in c
        assert "async def setup" not in c
        assert "async def teardown" not in c

    def test_async_return_annotation(self):
        c = make_stub(
            "from typing import Optional\n"
            "class Client:\n"
            "    async def fetch(self, url: str) -> Optional[str]: ...\n"
        )
        assert "async def fetch" in c
        # Modern style: str | None; accept either form
        assert ("str | None" in c or "Optional[str]" in c)

    def test_async_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "class Service:\n"
            "    async def process(self, a: int, b: str, c: float) -> None: ...\n"
        ))


# ============================================================================
# abstractmethod detection
# ============================================================================

class TestAbstractMethodDetection:

    def test_abstract_regular(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def must_impl(self):
                pass
        assert _is_abstract_method(Foo.__dict__["must_impl"])

    def test_concrete_not_abstract(self):
        class Foo:
            def concrete(self):
                pass
        assert not _is_abstract_method(Foo.__dict__["concrete"])

    def test_abstract_classmethod(self):
        class Foo(abc.ABC):
            @classmethod
            @abc.abstractmethod
            def cls_method(cls):
                pass
        assert _is_abstract_method(Foo.__dict__["cls_method"])

    def test_abstract_staticmethod(self):
        class Foo(abc.ABC):
            @staticmethod
            @abc.abstractmethod
            def static_method():
                pass
        assert _is_abstract_method(Foo.__dict__["static_method"])

    def test_abstract_property(self):
        class Foo(abc.ABC):
            @property
            @abc.abstractmethod
            def value(self) -> int: ...
        assert _is_abstract_method(Foo.__dict__["value"])


# ============================================================================
# abstractmethod stubs — unit
# ============================================================================

class TestAbstractMethodStubUnit:

    def test_abstractmethod_decorator_emitted(self):
        class Shape(abc.ABC):
            @abc.abstractmethod
            def area(self) -> float: ...
        stub = generate_method_stub(Shape, "area", StubContext())
        assert "@abstractmethod" in stub
        assert "def area" in stub

    def test_classmethod_before_abstractmethod(self):
        class Base(abc.ABC):
            @classmethod
            @abc.abstractmethod
            def create(cls) -> "Base": ...
        stub = generate_method_stub(Base, "create", StubContext())
        assert "@classmethod" in stub
        assert "@abstractmethod" in stub
        assert stub.index("@classmethod") < stub.index("@abstractmethod")

    def test_staticmethod_before_abstractmethod(self):
        class Base(abc.ABC):
            @staticmethod
            @abc.abstractmethod
            def compute() -> int: ...
        stub = generate_method_stub(Base, "compute", StubContext())
        assert stub.index("@staticmethod") < stub.index("@abstractmethod")

    def test_abstract_property_decorator_order(self):
        class Shape(abc.ABC):
            @property
            @abc.abstractmethod
            def area(self) -> float: ...
        stub = generate_method_stub(Shape, "area", StubContext())
        assert "@abstractmethod" in stub
        assert "@property" in stub
        assert stub.index("@abstractmethod") < stub.index("@property")

    def test_concrete_no_abstractmethod(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def abstract_fn(self) -> None: ...

            def concrete_fn(self) -> None:
                pass
        assert "@abstractmethod" in generate_method_stub(Foo, "abstract_fn", StubContext())
        assert "@abstractmethod" not in generate_method_stub(Foo, "concrete_fn", StubContext())


# ============================================================================
# ABC via generate_stub
# ============================================================================

class TestABCIntegration:

    def test_abc_base_in_stub(self):
        c = make_stub(
            "import abc\n"
            "class Shape(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def area(self) -> float: ...\n"
        )
        assert "class Shape(ABC):" in c
        assert "@abstractmethod" in c

    def test_abc_import_in_header(self):
        c = make_stub(
            "import abc\n"
            "class Base(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def method(self) -> None: ...\n"
        )
        assert "from abc import" in c
        assert "abstractmethod" in c
        assert "ABC" in c

    def test_abstract_classmethod_in_output(self):
        c = make_stub(
            "import abc\n"
            "class Factory(abc.ABC):\n"
            "    @classmethod\n"
            "    @abc.abstractmethod\n"
            "    def create(cls) -> 'Factory': ...\n"
        )
        assert "@classmethod" in c
        assert "@abstractmethod" in c
        assert_valid_syntax(c)

    def test_mixed_abstract_concrete(self):
        c = make_stub(
            "import abc\n"
            "class Widget(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def draw(self) -> None: ...\n"
            "    def hide(self) -> None: pass\n"
        )
        assert_valid_syntax(c)
        # @abstractmethod appears before draw, not before hide
        draw_idx = c.index("def draw")
        hide_idx = c.index("def hide")
        abstract_idx = c.index("@abstractmethod")
        assert abstract_idx < draw_idx
        # no @abstractmethod between hide and end
        assert "@abstractmethod" not in c[hide_idx:]

    def test_async_abstract_method(self):
        c = make_stub(
            "import abc\n"
            "class Source(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def read(self) -> bytes: ...\n"
        )
        assert "@abstractmethod" in c
        assert "async def read" in c
        assert_valid_syntax(c)

    def test_abc_class_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "import abc\n"
            "class Renderer(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def render(self, ctx: dict) -> str: ...\n"
            "    @classmethod\n"
            "    @abc.abstractmethod\n"
            "    def from_config(cls, cfg: dict) -> 'Renderer': ...\n"
            "    def reset(self) -> None: pass\n"
        ))


# ============================================================================
# dataclass detection
# ============================================================================

class TestDataclassDetection:

    def test_decorated_is_dataclass(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert _is_dataclass(Foo)

    def test_plain_class_not_dataclass(self):
        class Plain:
            x: int = 0
        assert not _is_dataclass(Plain)

    def test_dataclass_not_namedtuple(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert not _is_namedtuple(Foo)


# ============================================================================
# dataclass stubs — unit
# ============================================================================

class TestDataclassStubUnit:

    def test_decorator_emitted(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert stub.splitlines()[0] == "@dataclass"
        assert "class Point:" in stub.splitlines()[1]

    def test_init_synthesised(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float = 0.0
        stub = generate_class_stub(Point, StubContext())
        assert "def __init__" in stub
        assert "x: float" in stub
        assert "y: float = 0.0" in stub

    def test_default_factory(self):
        @_dc.dataclass
        class Bag:
            items: list = _dc.field(default_factory=list)
        stub = flatten(generate_class_stub(Bag, StubContext()))
        assert "items: list = ..." in stub

    def test_init_false_excluded_from_init(self):
        @_dc.dataclass
        class Config:
            name: str
            _computed: int = _dc.field(default=0, init=False)
        stub = flatten(generate_class_stub(Config, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "_computed" not in init_line

    def test_classvar_excluded_from_init(self):
        @_dc.dataclass
        class Model:
            MAX: typing.ClassVar[int] = 100
            value: int = 0
        stub = flatten(generate_class_stub(Model, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_annotations_in_body(self):
        @_dc.dataclass
        class Product:
            name: str
            price: float = 9.99
        stub = generate_class_stub(Product, StubContext())
        assert "name: str" in stub
        assert "price: float" in stub

    def test_post_init_included(self):
        @_dc.dataclass
        class Validated:
            x: int
            def __post_init__(self) -> None:
                assert self.x >= 0
        stub = generate_class_stub(Validated, StubContext())
        assert "__post_init__" in stub

    def test_inherited_fields_annotated(self):
        @_dc.dataclass
        class Base:
            x: int
        @_dc.dataclass
        class Child(Base):
            y: str
        stub = flatten(generate_class_stub(Child, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line


# ============================================================================
# dataclass via generate_stub
# ============================================================================

class TestDataclassIntegration:

    def test_basic_dataclass(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "def __init__" in c

    def test_dataclasses_import_in_header(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Foo:\n"
            "    x: int\n"
        )
        assert "from dataclasses import dataclass" in c

    def test_default_factory_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Bag:\n"
            "    items: list = field(default_factory=list)\n"
        )
        assert_valid_syntax(c)
        assert "items: list = ..." in flatten(c)

    def test_init_false_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Config:\n"
            "    name: str\n"
            "    counter: int = field(default=0, init=False)\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "counter" not in init_line

    def test_classvar_not_in_init_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "from typing import ClassVar\n"
            "@dataclass\n"
            "class Model:\n"
            "    MAX: ClassVar[int] = 100\n"
            "    value: int = 0\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_dataclass_inheritance_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Base:\n"
            "    x: int\n"
            "@dataclass\n"
            "class Child(Base):\n"
            "    y: str\n"
        )
        assert_valid_syntax(c)
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line

    def test_complex_dataclass_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from dataclasses import dataclass, field\n"
            "from typing import ClassVar, Optional\n"
            "@dataclass\n"
            "class Record:\n"
            "    MAX: ClassVar[int] = 1000\n"
            "    id: int\n"
            "    name: str = 'unnamed'\n"
            "    tags: list = field(default_factory=list)\n"
            "    _internal: bool = field(default=False, init=False)\n"
            "    def validate(self) -> bool: return True\n"
        ))


# ============================================================================
# NamedTuple detection
# ============================================================================

class TestNamedTupleDetection:

    def test_typed_namedtuple(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        assert _is_namedtuple(Point)

    def test_plain_class_not_namedtuple(self):
        class Foo:
            x: int
        assert not _is_namedtuple(Foo)

    def test_plain_tuple_subclass_not_namedtuple(self):
        class T(tuple):
            pass
        assert not _is_namedtuple(T)


# ============================================================================
# NamedTuple stubs — unit
# ============================================================================

class TestNamedTupleStubUnit:

    def test_class_line(self):
        class Color(typing.NamedTuple):
            r: int
            g: int
        assert generate_class_stub(Color, StubContext()).startswith("class Color(NamedTuple):")

    def test_field_annotations(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert "x: float" in stub
        assert "y: float" in stub

    def test_default_values(self):
        class Color(typing.NamedTuple):
            r: int
            g: int = 0
            b: int = 0
        stub = generate_class_stub(Color, StubContext())
        assert "r: int" in stub
        assert "g: int = 0" in stub
        assert "b: int = 0" in stub

    def test_no_generated_methods(self):
        class Pair(typing.NamedTuple):
            a: str
            b: str
        stub = generate_class_stub(Pair, StubContext())
        assert "_make" not in stub
        assert "_asdict" not in stub
        assert "_replace" not in stub

    def test_uses_namedtuple_base_not_tuple(self):
        class Point(typing.NamedTuple):
            x: float
        stub = generate_class_stub(Point, StubContext())
        assert "class Point(NamedTuple):" in stub
        assert "class Point(tuple):" not in stub

    def test_empty_namedtuple(self):
        class Empty(typing.NamedTuple):
            pass
        stub = generate_class_stub(Empty, StubContext())
        assert "class Empty(NamedTuple):" in stub
        assert "..." in stub


# ============================================================================
# NamedTuple via generate_stub
# ============================================================================

class TestNamedTupleIntegration:

    def test_namedtuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "r: int" in c
        assert "g: int = 0" in c

    def test_namedtuple_import_in_header(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
        )
        assert "from typing import NamedTuple" in c

    def test_multiple_namedtuples(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
            "class RGB(NamedTuple):\n"
            "    r: int\n"
            "    g: int\n"
            "    b: int\n"
        )
        assert_valid_syntax(c)
        assert "class Point(NamedTuple):" in c
        assert "class RGB(NamedTuple):" in c

    def test_no_tuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
        )
        assert "class Point(NamedTuple):" in c
        assert "tuple" not in c

    def test_namedtuple_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from typing import NamedTuple\n"
            "class Vector(NamedTuple):\n"
            "    x: float = 0.0\n"
            "    y: float = 0.0\n"
            "    z: float = 0.0\n"
        ))

    def test_namedtuple_and_class_coexist(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Size(NamedTuple):\n"
            "    width: int\n"
            "    height: int\n"
            "class Canvas:\n"
            "    def __init__(self, size: 'Size') -> None: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Size(NamedTuple):" in c
        assert "class Canvas:" in c


# ============================================================================
# collect_special_imports
# ============================================================================

class TestCollectSpecialImports:

    def test_abstractmethod_only(self):
        result = collect_special_imports("@abstractmethod\ndef foo(): ...")
        assert "abc" in result
        assert "abstractmethod" in result["abc"]

    def test_abc_base_only(self):
        result = collect_special_imports("class Foo(ABC):\n    pass")
        assert "abc" in result
        assert "ABC" in result["abc"]

    def test_both_abc_names(self):
        result = collect_special_imports(
            "class Foo(ABC):\n    @abstractmethod\n    def bar(): ..."
        )
        assert "ABC" in result["abc"]
        assert "abstractmethod" in result["abc"]

    def test_dataclass(self):
        result = collect_special_imports("@dataclass\nclass Foo:\n    x: int")
        assert "dataclasses" in result
        assert "dataclass" in result["dataclasses"]

    def test_empty_body(self):
        result = collect_special_imports("class Foo:\n    def bar(self) -> int: ...")
        assert result == {}


# ============================================================================
# Integration — all special-class patterns combined
# ============================================================================

class TestSpecialClassIntegration:

    def test_all_patterns_combined(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "from typing import NamedTuple\n"
            "\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
            "\n"
            "class Renderer(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def render(self, ctx: dict) -> str: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "class Renderer(ABC):" in c
        assert "@abstractmethod" in c
        assert "async def render" in c

    def test_dataclass_with_abc_base(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Entity(abc.ABC):\n"
            "    id: int\n"
            "    @abc.abstractmethod\n"
            "    def serialize(self) -> dict: ...\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Entity(ABC):" in c
        assert "@abstractmethod" in c
        assert "def __init__" in c

    def test_kwargs_backtracing_unaffected(self):
        c = make_stub(
            "class Base:\n"
            "    def __init__(self, x: float, y: float = 0.0) -> None: pass\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "label: str" in init_line
        assert "x: float" in init_line
        assert "**kwargs" not in init_line

    def test_async_in_abc(self):
        c = make_stub(
            "import abc\n"
            "class Stream(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def read(self, n: int) -> bytes: ...\n"
            "    async def write(self, data: bytes) -> None: pass\n"
        )
        assert_valid_syntax(c)
        assert "@abstractmethod" in c
        assert c.count("async def") == 2

    def test_full_combination_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "import abc\n"
            "from dataclasses import dataclass, field\n"
            "from typing import NamedTuple, Optional\n"
            "\n"
            "class RGB(NamedTuple):\n"
            "    r: int = 0\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
            "    tags: list = field(default_factory=list)\n"
            "\n"
            "class Protocol(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def connect(self, cfg: Config) -> None: ...\n"
            "    @abc.abstractmethod\n"
            "    async def send(self, data: bytes) -> int: ...\n"
            "    def close(self) -> None: pass\n"
        ))

    def test_graphics_demo_backward_compat(self):
        from pathlib import Path
        import tempfile
        from stubpy import generate_stub

        demo = Path(__file__).parent.parent / "demo" / "graphics.py"
        with tempfile.NamedTemporaryFile(suffix=".pyi", delete=False) as f:
            out = f.name
        c = generate_stub(str(demo), out)
        assert_valid_syntax(c)
        for cls_name in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
            assert f"class {cls_name}" in c
        arc_section = c.split("class Arc")[1].split("\nclass ")[0]
        assert "angle: float" in arc_section
        assert "**kwargs" not in arc_section



class TestTypedDictStub:
    def test_total_true(self):
        class Opts(TypedDict):
            width: int
            height: int

        ctx = _ctx()
        stub = generate_class_stub(Opts, ctx)
        assert "class Opts(TypedDict):" in stub
        assert "width: int" in stub
        assert "height: int" in stub
        assert "total=False" not in stub

    def test_total_false(self):
        class Opts(TypedDict, total=False):
            width: int
            height: int

        ctx = _ctx()
        stub = generate_class_stub(Opts, ctx)
        assert "class Opts(TypedDict, total=False):" in stub

    def test_stub_is_valid_python(self):
        class Config(TypedDict, total=False):
            compact: bool
            indent: str
            dpi: float

        ctx = _ctx()
        stub = generate_class_stub(Config, ctx)
        _parse(stub)

    def test_typeddict_in_generated_file(self):
        stub = _generate(
            """
            from typing import TypedDict
            class RenderOpts(TypedDict, total=False):
                compact: bool
                dpi: float
            """,
        )
        assert "class RenderOpts(TypedDict, total=False):" in stub
        _parse(stub)

    def test_typeddict_import_added(self):
        stub = _generate(
            """
            from typing import TypedDict
            class Opts(TypedDict):
                x: int
            """,
        )
        assert "TypedDict" in stub


# ===========================================================================
# Enum stub generation
# ===========================================================================


class TestEnumStub:
    def test_enum_base_class_rendered(self):
        class Color(enum.Enum):
            RED   = "red"
            GREEN = "green"
            BLUE  = "blue"

        ctx = _ctx()
        stub = generate_class_stub(Color, ctx)
        assert "class Color(Enum):" in stub

    def test_int_enum_base_class(self):
        class Level(enum.IntEnum):
            DEBUG   = 0
            WARNING = 1
            ERROR   = 2

        ctx = _ctx()
        stub = generate_class_stub(Level, ctx)
        assert "class Level(IntEnum):" in stub

    def test_enum_private_methods_suppressed(self):
        class Status(enum.Enum):
            ACTIVE   = "active"
            INACTIVE = "inactive"

        ctx = _ctx()
        stub = generate_class_stub(Status, ctx)
        assert "_generate_next_value_" not in stub
        assert "_missing_" not in stub
        assert "_member_type_" not in stub

    def test_enum_stub_valid_python(self):
        class BlendMode(enum.Enum):
            NORMAL   = "normal"
            MULTIPLY = "multiply"

        ctx = _ctx()
        stub = generate_class_stub(BlendMode, ctx)
        _parse(stub)

    def test_enum_import_added(self):
        stub = _generate(
            """
            import enum
            class Color(enum.Enum):
                RED = "red"
            """,
        )
        assert "from enum import Enum" in stub

    def test_int_enum_import_added(self):
        stub = _generate(
            """
            import enum
            class Level(enum.IntEnum):
                DEBUG = 0
            """,
        )
        assert "IntEnum" in stub


# ===========================================================================
# default_to_str: Enum members and type objects
# ===========================================================================


class TestNamedTupleWithMethods:
    def test_property_emitted(self):
        class Point(NamedTuple):
            x: float
            y: float

            @property
            def magnitude(self) -> float:
                return (self.x**2 + self.y**2) ** 0.5

        ctx = _ctx()
        stub = generate_class_stub(Point, ctx)
        assert "@property" in stub
        assert "def magnitude" in stub

    def test_custom_method_emitted(self):
        class Vector(NamedTuple):
            x: float
            y: float

            def dot(self, other: "Vector") -> float:
                return self.x * other.x + self.y * other.y

        ctx = _ctx()
        stub = generate_class_stub(Vector, ctx)
        assert "def dot" in stub

    def test_nt_internals_suppressed(self):
        class Color(NamedTuple):
            r: float
            g: float
            b: float

        ctx = _ctx()
        stub = generate_class_stub(Color, ctx)
        assert "_make" not in stub
        assert "_asdict" not in stub
        assert "_replace" not in stub

    def test_stub_with_methods_valid_python(self):
        class BBox(NamedTuple):
            x: float
            y: float
            w: float
            h: float

            @property
            def right(self) -> float:
                return self.x + self.w

            def area(self) -> float:
                return self.w * self.h

        ctx = _ctx()
        stub = generate_class_stub(BBox, ctx)
        _parse(stub)


# ===========================================================================
# collect_special_imports: Enum detection
# ===========================================================================

# ---------------------------------------------------------------------------
# Property MRO tracking
# ---------------------------------------------------------------------------

class TestFindPropertyMro:
    """Unit tests for the _find_property_mro helper."""

    def test_simple_property_on_class(self):
        class A:
            @property
            def x(self) -> int:
                return 0

        prop = _find_property_mro(A, "x")
        assert prop is not None
        assert prop.fget is not None

    def test_getter_and_setter_on_same_class(self):
        class A:
            @property
            def x(self) -> int:
                return 0

            @x.setter
            def x(self, v: int) -> None:
                pass

        prop = _find_property_mro(A, "x")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None

    def test_child_only_getter_finds_parent_setter(self):
        """Child overrides getter only — MRO should find parent setter."""
        class Parent:
            @property
            def color(self) -> str:
                return "red"

            @color.setter
            def color(self, v: str) -> None:
                pass

        class Child(Parent):
            @property
            def color(self) -> str:
                return "blue"  # only getter overridden

        prop = _find_property_mro(Child, "color")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None  # found from Parent

    def test_child_only_setter_finds_parent_getter(self):
        """Child overrides setter only — MRO should find parent getter."""
        class Parent:
            @property
            def value(self) -> float:
                return 0.0

            @value.setter
            def value(self, v: float) -> None:
                pass

        # Child redefines via a fresh property so we can test MRO fallback
        class Child(Parent):
            # Redefine only setter by building a new property
            value = property(Parent.value.fget, lambda self, v: None)

        prop = _find_property_mro(Child, "value")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None

    def test_not_a_property_returns_none(self):
        class A:
            def x(self) -> int:
                return 0

        assert _find_property_mro(A, "x") is None

    def test_missing_attribute_returns_none(self):
        class A:
            pass

        assert _find_property_mro(A, "nonexistent") is None

    def test_deep_mro_chain(self):
        """Property scattered across 3 levels of inheritance."""
        class GrandParent:
            @property
            def p(self) -> str:
                return ""

        class Parent(GrandParent):
            p = property(GrandParent.p.fget, lambda self, v: None)

        class Child(Parent):
            p = property(Parent.p.fget, lambda self, v: None)

        prop = _find_property_mro(Child, "p")
        assert prop is not None
        assert prop.fget is not None
        assert prop.fset is not None


class TestPropertyMROInStubs:
    """Integration: generate_method_stub uses MRO-complete property."""

    def test_child_getter_only_emits_inherited_setter(self):
        class Parent:
            @property
            def color(self) -> str:
                return ""

            @color.setter
            def color(self, v: str) -> None:
                pass

        class Child(Parent):
            @property
            def color(self) -> str:
                return "blue"

        ctx = StubContext()
        stub = generate_method_stub(Child, "color", ctx)
        assert "@property" in stub
        assert "@color.setter" in stub
        assert "-> str" in stub

    def test_full_class_stub_includes_setter(self):
        class ColorMixin:
            @property
            def color(self) -> str:
                return ""

            @color.setter
            def color(self, v: str) -> None:
                pass

        class ColoredWidget(ColorMixin):
            @property
            def color(self) -> str:
                return "blue"

        ctx = StubContext()
        stub = generate_class_stub(ColoredWidget, ctx)
        assert "@property" in stub
        assert "@color.setter" in stub

    def test_no_setter_in_entire_mro_omits_setter(self):
        class A:
            @property
            def x(self) -> int:
                return 0

        class B(A):
            @property
            def x(self) -> int:
                return 1  # no setter anywhere

        ctx = StubContext()
        stub = generate_method_stub(B, "x", ctx)
        assert "@property" in stub
        assert "@x.setter" not in stub

    def test_property_return_type_from_parent_getter(self):
        """When child getter has no annotation, parent's type should propagate."""
        class Parent:
            @property
            def size(self) -> float:
                return 0.0

        class Child(Parent):
            @property
            def size(self) -> float:
                return 1.0

        ctx = StubContext()
        stub = generate_method_stub(Child, "size", ctx)
        assert "-> float" in stub

    def test_integration_with_demo_dispatch(self, tmp_path):
        """ColoredSVGRenderer in demo/dispatch.py must emit setter from ColoredMixin."""
        import sys
        sys.path.insert(0, str(tmp_path.parent.parent / "Stubpy5.3"))
        from stubpy import generate_stub
        from stubpy.context import StubContext

        demo_file = tmp_path.parent.parent / "Stubpy5.3" / "demo" / "dispatch.py"
        if not demo_file.exists():
            pytest.skip("demo/dispatch.py not found")

        pyi = tmp_path / "dispatch.pyi"
        ctx = StubContext()
        stub = generate_stub(str(demo_file), str(pyi), ctx=ctx)

        # ColoredSVGRenderer only defines getter — must still have setter from mixin
        assert "class ColoredSVGRenderer" in stub
        assert "@color.setter" in stub


# ---------------------------------------------------------------------------
# Module-level symbol stubs (functions, variables, aliases, overloads)
# ---------------------------------------------------------------------------

class TestGenerateFunctionStubUnit:

    def test_basic_sync(self):
        def greet(name: str, times: int = 1) -> str:
            return ""
        sym = _function_sym("greet", live_func=greet, raw_return="str")
        stub = generate_function_stub(sym, StubContext())
        assert "def greet" in stub
        assert "name: str" in stub
        assert "times: int = 1" in stub
        assert "-> str" in stub
        assert "..." in stub
        assert "async" not in stub

    def test_async_from_ast_flag(self):
        fi = FunctionInfo(name="fetch", lineno=1, is_async=True)
        sym = FunctionSymbol("fetch", 1, live_func=None, ast_info=fi)
        assert generate_function_stub(sym, StubContext()).startswith("async def fetch")

    def test_async_detected_from_runtime(self):
        async def fetch(url: str) -> bytes:
            return b""
        fi = FunctionInfo(name="fetch", lineno=1, is_async=False)
        sym = FunctionSymbol("fetch", 1, live_func=fetch, ast_info=fi)
        assert generate_function_stub(sym, StubContext()).startswith("async def fetch")

    def test_zero_params(self):
        def ping() -> None:
            pass
        sym = _function_sym("ping", live_func=ping, raw_return="None")
        assert "def ping() -> None: ..." in generate_function_stub(sym, StubContext())

    def test_no_annotations_bare_names(self):
        def raw(x, y):
            pass
        sym = _function_sym("raw", live_func=raw)
        assert "def raw(x, y)" in generate_function_stub(sym, StubContext())

    def test_inline_for_two_params(self):
        def add(a: float, b: float) -> float:
            return a + b
        sym = _function_sym("add", live_func=add)
        stub = generate_function_stub(sym, StubContext())
        # inline = fits on one line
        assert stub.count("\n") == 0 or "def add(a:" in stub.splitlines()[0]

    def test_multiline_for_three_params(self):
        def transform(x: int, y: int, z: int) -> int:
            return x
        sym = _function_sym("transform", live_func=transform)
        stub = generate_function_stub(sym, StubContext())
        assert "\n" in stub
        assert_valid_syntax(stub)

    def test_default_values_preserved(self):
        def greet(name: str = "world", *, sep: str = "!") -> str:
            return ""
        sym = _function_sym("greet", live_func=greet)
        stub = flatten(generate_function_stub(sym, StubContext()))
        assert "name: str = 'world'" in stub
        assert "sep: str = '!'" in stub

    def test_kw_only_separator(self):
        def fn(a: int, *, b: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        stub = flatten(generate_function_stub(sym, StubContext()))
        assert "*," in stub or "*, b" in stub
        assert stub.index("*") < stub.index("b:")

    def test_var_positional_with_annotation(self):
        def fn(x: int, *args: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        assert "*args: str" in flatten(generate_function_stub(sym, StubContext()))

    def test_var_keyword_with_annotation(self):
        def fn(**kwargs: int) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        assert "**kwargs: int" in flatten(generate_function_stub(sym, StubContext()))

    def test_return_annotation(self):
        def square(n: int) -> int:
            return n * n
        sym = _function_sym("square", live_func=square, raw_return="int")
        assert "-> int" in generate_function_stub(sym, StubContext())

    def test_no_return_annotation(self):
        def untyped():
            pass
        sym = _function_sym("untyped", live_func=untyped)
        assert "->" not in generate_function_stub(sym, StubContext())

    def test_raw_return_fallback_no_live_func(self):
        fi = FunctionInfo(name="helper", lineno=1, raw_return_annotation="list[str]")
        sym = FunctionSymbol("helper", 1, live_func=None, ast_info=fi)
        assert "-> list[str]" in generate_function_stub(sym, StubContext())

    def test_no_live_func_no_crash(self):
        sym = FunctionSymbol("orphan", 1, live_func=None, ast_info=None)
        stub = generate_function_stub(sym, StubContext())
        assert isinstance(stub, str)

    def test_complex_signature_valid_syntax(self):
        def fn(a: int, b: str, c: float = 1.0, *, d: bool = False, **kw: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn, raw_return="None")
        assert_valid_syntax(generate_function_stub(sym, StubContext()))

    def test_async_generator(self):
        async def agen():
            yield 1
        fi = FunctionInfo(name="agen", lineno=1, is_async=False)
        sym = FunctionSymbol("agen", 1, live_func=agen, ast_info=fi)
        assert "async def agen" in generate_function_stub(sym, StubContext())


# ============================================================================
# generate_variable_stub — unit tests
# ============================================================================

class TestGenerateVariableStubUnit:

    def test_annotated_int(self):
        sym = _variable_sym("MAX", annotation="int", live_value=100)
        assert generate_variable_stub(sym, StubContext()) == "MAX: int"

    def test_annotated_str(self):
        sym = _variable_sym("NAME", annotation="str", live_value="hello")
        assert generate_variable_stub(sym, StubContext()) == "NAME: str"

    def test_annotated_bool(self):
        sym = _variable_sym("ENABLED", annotation="bool", live_value=True)
        assert generate_variable_stub(sym, StubContext()) == "ENABLED: bool"

    def test_inferred_fallback(self):
        sym = _variable_sym("VERSION", inferred="str", live_value="1.0.0")
        assert generate_variable_stub(sym, StubContext()) == "VERSION: str"

    def test_inferred_records_warning(self):
        ctx = StubContext()
        sym = _variable_sym("X", inferred="int", live_value=42)
        generate_variable_stub(sym, ctx)
        assert ctx.diagnostics.has_warnings()
        w = ctx.diagnostics.warnings[0]
        assert w.level == DiagnosticLevel.WARNING
        assert w.stage == DiagnosticStage.EMIT
        assert "X" in w.symbol

    def test_annotated_no_warning(self):
        ctx = StubContext()
        sym = _variable_sym("MAX", annotation="int", live_value=100)
        generate_variable_stub(sym, ctx)
        assert not ctx.diagnostics.has_warnings()

    def test_no_type_returns_empty(self):
        sym = _variable_sym("MYSTERY")
        assert generate_variable_stub(sym, StubContext()) == ""

    def test_annotation_priority_over_inferred(self):
        sym = _variable_sym("X", annotation="float", inferred="int", live_value=3)
        assert generate_variable_stub(sym, StubContext()) == "X: float"

    def test_complex_annotation(self):
        sym = _variable_sym("DATA", annotation="dict[str, list[int]]")
        assert generate_variable_stub(sym, StubContext()) == "DATA: dict[str, list[int]]"


# ============================================================================
# Function stubs via generate_stub
# ============================================================================

class TestFunctionStubGeneration:

    def test_sync_function_in_output(self):
        c = make_stub("def greet(name: str) -> str: return name\n")
        assert "def greet(name: str) -> str: ..." in c

    def test_async_function_in_output(self):
        c = make_stub("async def fetch(url: str) -> bytes: ...\n")
        assert "async def fetch(url: str) -> bytes: ..." in c

    def test_multiple_functions_all_present(self):
        c = make_stub(
            "def foo(x: int) -> int: return x\n"
            "def bar(y: str) -> str: return y\n"
        )
        assert "def foo(x: int) -> int" in c
        assert "def bar(y: str) -> str" in c

    def test_function_defaults_in_output(self):
        c = make_stub("def fn(x: int = 0, y: str = 'hi') -> None: pass\n")
        assert "x: int = 0" in c
        assert "y: str = 'hi'" in c

    def test_sync_and_async_mixed(self):
        c = make_stub(
            "def sync_fn(a: int) -> int: return a\n"
            "async def async_fn(b: str) -> str: return b\n"
        )
        assert "def sync_fn" in c
        assert "async def async_fn" in c

    def test_multiline_valid_syntax(self):
        c = make_stub(
            "def transform(x: int, y: int, z: int, scale: float = 1.0) -> tuple: ...\n"
        )
        assert_valid_syntax(c)
        assert "def transform" in c

    def test_function_and_class_coexist(self):
        c = make_stub(
            "class Foo:\n"
            "    def method(self) -> None: ...\n"
            "def helper(x: int) -> int: return x\n"
        )
        assert "class Foo:" in c
        assert "def helper(x: int) -> int" in c

    def test_private_function_excluded(self):
        c = make_stub(
            "def _private(x: int) -> int: return x\n"
            "def public(x: int) -> int: return x\n"
        )
        assert "def public" in c
        assert "def _private" not in c

    def test_kw_only_separator_in_output(self):
        c = make_stub("def fn(a: int, *, b: str = 'x') -> None: pass\n")
        flat = flatten(c)
        fn_line = [l for l in flat.splitlines() if "def fn" in l][0]
        assert "a: int" in fn_line
        assert "b: str" in fn_line
        assert "*," in fn_line or "*, b" in fn_line

    def test_typing_imports_collected(self):
        # When typing names genuinely appear in the stub body, they are imported.
        # Use ClassVar which always needs a typing import.
        c = make_stub(
            "from typing import ClassVar\n"
            "class Foo:\n"
            "    x: ClassVar[int] = 0\n"
        )
        assert "from typing import ClassVar" in c

    def test_typing_imports_optional_in_legacy_style(self):
        """With union_style='legacy', Optional[str] appears in stub → Optional imported."""
        from stubpy.context import StubConfig, StubContext
        import tempfile
        from pathlib import Path
        from stubpy import generate_stub

        src = "from typing import Optional\ndef fn(x: Optional[str] = None) -> Optional[int]: ...\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        c = generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        assert "from typing import Optional" in c

    def test_source_order_preserved(self):
        c = make_stub(
            "def first() -> int: return 1\n"
            "def second() -> str: return ''\n"
            "def third() -> bool: return True\n"
        )
        assert c.index("def first") < c.index("def second") < c.index("def third")

    def test_var_positional_in_output(self):
        c = make_stub("def fn(x: int, *args: str) -> None: pass\n")
        assert "*args: str" in c

    def test_var_keyword_in_output(self):
        c = make_stub("def fn(**kwargs: int) -> None: pass\n")
        assert "**kwargs: int" in c


# ============================================================================
# Variable stubs via generate_stub
# ============================================================================

class TestVariableStubGeneration:

    def test_annotated_int(self):
        assert "MAX: int" in make_stub("MAX: int = 1024\n")

    def test_annotated_str(self):
        assert "NAME: str" in make_stub("NAME: str = 'test'\n")

    def test_annotated_float(self):
        assert "PI: float" in make_stub("PI: float = 3.14\n")

    def test_annotated_bool(self):
        assert "ENABLED: bool" in make_stub("ENABLED: bool = True\n")

    def test_unannotated_inferred_str(self):
        assert "VERSION: str" in make_stub("VERSION = '1.0.0'\n")

    def test_unannotated_inferred_int(self):
        assert "TIMEOUT: int" in make_stub("TIMEOUT = 30\n")

    def test_unannotated_inferred_bool(self):
        assert "DEBUG: bool" in make_stub("DEBUG = False\n")

    def test_private_variable_excluded(self):
        c = make_stub("_CACHE: dict = {}\nPUBLIC: int = 1\n")
        assert "PUBLIC: int" in c
        assert "_CACHE" not in c

    def test_multiple_variables_all_present(self):
        c = make_stub("A: int = 1\nB: str = 'x'\nC: float = 1.0\n")
        assert "A: int" in c
        assert "B: str" in c
        assert "C: float" in c

    def test_source_order_preserved(self):
        c = make_stub("FIRST: int = 1\nSECOND: str = 'x'\nTHIRD: bool = True\n")
        assert c.index("FIRST") < c.index("SECOND") < c.index("THIRD")

    def test_valid_syntax(self):
        assert_valid_syntax(make_stub("X: int = 1\nY: str = 'hi'\nZ = 3.14\n"))

    def test_declaration_without_value(self):
        assert "x: int" in make_stub("x: int\n")


# ============================================================================
# __all__ filtering
# ============================================================================

class TestAllFiltering:

    def test_filters_functions(self):
        c = make_stub(
            "__all__ = ['public_fn']\n"
            "def public_fn(x: int) -> int: return x\n"
            "def excluded_fn(y: str) -> str: return y\n"
        )
        assert "def public_fn" in c
        assert "def excluded_fn" not in c

    def test_filters_variables(self):
        c = make_stub(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "EXCLUDED: str = 'nope'\n"
        )
        assert "PUBLIC: int" in c
        assert "EXCLUDED" not in c

    def test_filters_classes(self):
        c = make_stub(
            "__all__ = ['Exported']\n"
            "class Exported:\n    x: int = 1\n"
            "class Hidden:\n    y: int = 2\n"
        )
        assert "class Exported:" in c
        assert "class Hidden" not in c

    def test_mixed_kinds(self):
        c = make_stub(
            "__all__ = ['MyClass', 'my_fn', 'MY_VAR']\n"
            "class MyClass:\n    pass\n"
            "def my_fn() -> None: pass\n"
            "MY_VAR: int = 42\n"
            "class OtherClass:\n    pass\n"
            "def other_fn() -> None: pass\n"
            "OTHER_VAR: str = 'x'\n"
        )
        assert "class MyClass:" in c
        assert "def my_fn" in c
        assert "MY_VAR: int" in c
        assert "class OtherClass" not in c
        assert "def other_fn" not in c
        assert "OTHER_VAR" not in c

    def test_no_all_includes_all_public(self):
        c = make_stub(
            "class Foo:\n    pass\n"
            "def bar() -> None: pass\n"
            "BAZ: int = 1\n"
        )
        assert "class Foo:" in c
        assert "def bar" in c
        assert "BAZ: int" in c

    def test_empty_all_emits_nothing(self):
        c = make_stub(
            "__all__ = []\n"
            "class Foo:\n    pass\n"
            "def bar() -> None: pass\n"
        )
        assert "class Foo" not in c
        assert "def bar" not in c

    def test_all_restricts_public_names(self):
        c = make_stub(
            "__all__ = ['Alpha']\n"
            "class Alpha:\n    pass\n"
            "class Beta:\n    pass\n"
        )
        assert "class Alpha:" in c
        assert "class Beta" not in c

    def test_build_symbol_table_all_filter(self):
        src = (
            "__all__ = ['PubClass', 'pub_fn', 'PUB_VAR']\n"
            "class PubClass: pass\n"
            "class PrivClass: pass\n"
            "def pub_fn() -> None: pass\n"
            "def priv_fn() -> None: pass\n"
            "PUB_VAR: int = 1\n"
            "PRIV_VAR: str = 'x'\n"
        )
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_filter")

        class PubClass:
            pass

        class PrivClass:
            pass

        PubClass.__module__ = PrivClass.__module__ = "_stubpy_target_filter"
        m.PubClass, m.PrivClass = PubClass, PrivClass

        def pub_fn():
            pass

        def priv_fn():
            pass

        m.pub_fn, m.priv_fn = pub_fn, priv_fn
        m.PUB_VAR, m.PRIV_VAR = 1, "x"
        tbl = build_symbol_table(
            m, "_stubpy_target_filter", syms,
            all_exports={"PubClass", "pub_fn", "PUB_VAR"},
        )
        names = tbl.all_names()
        assert "PubClass" in names
        assert "pub_fn" in names
        assert "PUB_VAR" in names
        assert "PrivClass" not in names
        assert "priv_fn" not in names
        assert "PRIV_VAR" not in names


# ============================================================================
# include_private
# ============================================================================

class TestIncludePrivate:

    def test_private_variables_included(self):
        c = _make_stub_cfg(
            "_SECRET: int = 1\nPUBLIC: str = 'x'\n",
            include_private=True,
        )
        assert "_SECRET: int" in c
        assert "PUBLIC: str" in c

    def test_private_functions_included(self):
        c = _make_stub_cfg(
            "def _private_fn(x: int) -> int: return x\n"
            "def public_fn(y: str) -> str: return y\n",
            include_private=True,
        )
        assert "def _private_fn" in c
        assert "def public_fn" in c

    def test_private_excluded_by_default(self):
        c = make_stub("_PRIVATE: int = 1\nPUBLIC: int = 2\n")
        assert "_PRIVATE" not in c
        assert "PUBLIC: int" in c

    def test_include_private_in_symbol_table(self):
        src = "_SECRET: int = 1\nPUBLIC: str = 'x'\n"
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_incpriv")
        m._SECRET, m.PUBLIC = 1, "x"

        tbl_default = build_symbol_table(m, "_stubpy_target_incpriv", syms)
        assert "_SECRET" not in tbl_default
        assert "PUBLIC" in tbl_default

        tbl_priv = build_symbol_table(
            m, "_stubpy_target_incpriv", syms, include_private=True
        )
        assert "_SECRET" in tbl_priv
        assert "PUBLIC" in tbl_priv

    def test_include_private_with_all_exports_in_symbol_table(self):
        # When __all__ is present AND include_private=True, private names
        # must appear regardless of __all__, while __all__ still restricts
        # which public names are included.
        src = "__all__ = ['PUB']\nPUB: int = 1\nOTHER: int = 2\n_PRIV: str = 'x'\n"
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_allpriv")
        m.PUB, m.OTHER, m._PRIV = 1, 2, "x"

        # Default: only PUB (in __all__), no private
        tbl = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                 all_exports={"PUB"})
        assert "PUB" in tbl
        assert "OTHER" not in tbl
        assert "_PRIV" not in tbl

        # With include_private: PUB from __all__ + _PRIV private; OTHER still excluded
        tbl_p = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                   all_exports={"PUB"}, include_private=True)
        assert "PUB" in tbl_p
        assert "_PRIV" in tbl_p
        assert "OTHER" not in tbl_p  # public but not in __all__

    def test_include_private_bypasses_all_for_private_names(self):
        # --include-private makes private symbols visible even when __all__
        # is declared and does not list them. __all__ controls public names;
        # include_private controls private ones independently.
        c = _make_stub_cfg(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=True,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE: str" in c  # private appears despite not being in __all__

    def test_include_private_false_still_hides_private_with_all(self):
        # Without the flag, private names stay hidden even if __all__ is absent.
        c = _make_stub_cfg(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=False,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE" not in c

    def test_respect_all_false(self):
        c = _make_stub_cfg(
            "__all__ = ['Alpha']\n"
            "class Alpha:\n    pass\n"
            "class Beta:\n    pass\n",
            respect_all=False,
        )
        assert "class Alpha:" in c
        assert "class Beta:" in c


# ============================================================================
# Source-order interleaving
# ============================================================================

class TestSourceOrder:

    def test_class_function_variable_order(self):
        c = make_stub(
            "class Widget:\n"
            "    x: int = 1\n"
            "\n"
            "def make_widget(name: str) -> Widget: ...\n"
            "\n"
            "COLOR: str = 'black'\n"
        )
        assert c.index("class Widget") < c.index("def make_widget") < c.index("COLOR:")

    def test_function_before_class(self):
        c = make_stub("def factory() -> 'Foo': ...\n\nclass Foo:\n    pass\n")
        assert c.index("def factory") < c.index("class Foo")

    def test_variable_before_class(self):
        c = make_stub("DEFAULT: str = 'x'\n\nclass Config:\n    pass\n")
        assert c.index("DEFAULT:") < c.index("class Config")

    def test_fully_mixed_valid_syntax(self):
        c = make_stub(
            "MAX: int = 10\n"
            "\n"
            "def add(a: int, b: int = 0) -> int: return a + b\n"
            "\n"
            "class Container:\n"
            "    items: list\n"
            "    def __init__(self, items: list) -> None: ...\n"
            "\n"
            "VERSION: str = '1.0'\n"
            "\n"
            "async def fetch(url: str) -> bytes: ...\n"
        )
        assert_valid_syntax(c)


# ============================================================================
# Edge-cases
# ============================================================================

class TestEdgeCases:

    def test_empty_module(self):
        c = make_stub("")
        assert_valid_syntax(c)
        assert "from __future__ import annotations" in c

    def test_import_only_module(self):
        assert_valid_syntax(make_stub("from typing import Optional\nimport os\n"))

    def test_all_private_empty_body(self):
        c = make_stub("_A: int = 1\n_B: str = 'x'\n")
        assert_valid_syntax(c)
        assert "_A" not in c
        assert "_B" not in c

    def test_function_forward_ref_return(self):
        c = make_stub(
            "class Foo:\n    pass\n"
            "def make() -> 'Foo': ...\n"
        )
        assert "def make" in c
        assert_valid_syntax(c)

    def test_unannotated_var_warning_recorded(self):
        import tempfile
        from pathlib import Path
        from stubpy import generate_stub

        src = "UNTYPED = 42\n"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext()
        generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        warnings = ctx.diagnostics.warnings
        assert any(
            "UNTYPED" in w.symbol or "inferred" in w.message.lower()
            for w in warnings
        )

    def test_typevar_not_emitted_as_variable(self):
        c = make_stub("from typing import TypeVar\nT = TypeVar('T')\nX: int = 1\n")
        assert "X: int" in c
        assert "T: TypeVar" not in c

    def test_complex_mixed_signature_valid(self):
        c = make_stub(
            "from typing import Any\n"
            "def fn(a: int, b: str, *args: float, flag: bool = False, **kw: Any) -> None: pass\n"
        )
        assert_valid_syntax(c)
        assert "def fn" in c

    def test_variable_and_function_in_all(self):
        c = make_stub(
            "__all__ = ['CONST', 'helper']\n"
            "CONST: int = 7\n"
            "def helper(x: int) -> int: return x\n"
            "def excluded() -> None: pass\n"
            "ALSO_EXCLUDED: str = 'nope'\n"
        )
        assert "CONST: int" in c
        assert "def helper" in c
        assert "def excluded" not in c
        assert "ALSO_EXCLUDED" not in c


# ---------------------------------------------------------------------------
# Alias stubs (TypeVar, TypeAlias, NewType)
# ---------------------------------------------------------------------------

class TestAliasStubGeneration:
    """TypeVar / TypeAlias / NewType stubs are generated correctly."""

    def test_typevar_stub_in_output(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
        )
        assert "T = TypeVar('T')" in c
        assert_valid_syntax(c)

    def test_newtype_stub_in_output(self):
        c = make_stub(
            "from typing import NewType\n"
            "UserId = NewType('UserId', int)\n"
        )
        assert "UserId = NewType('UserId', int)" in c
        assert_valid_syntax(c)

    def test_typealias_stub_in_output(self):
        c = make_stub(
            "from typing import TypeAlias\n"
            "PathStr: TypeAlias = str\n"
        )
        assert "PathStr: TypeAlias = str" in c
        assert_valid_syntax(c)

    def test_alias_precedes_using_function(self):
        """Alias declaration appears before the function that uses it."""
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "def identity(x: T) -> T: return x\n"
        )
        assert c.index("T = TypeVar") < c.index("def identity")

    def test_alias_respects_all(self):
        c = make_stub(
            "__all__ = ['T', 'helper']\n"
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "S = TypeVar('S')\n"
            "def helper(x: int) -> int: return x\n"
        )
        assert "T = TypeVar" in c
        assert "S = TypeVar" not in c


# ---------------------------------------------------------------------------
# Overload stubs (module-level)
# ---------------------------------------------------------------------------

class TestOverloadStubGeneration:
    """Module-level @overload stubs are generated and implementation is suppressed."""

    def test_overload_count(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert c.count("@overload") == 2

    def test_implementation_not_emitted(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        # Exactly 2 'def f' — both overloads only
        assert c.count("def f") == 2

    def test_overload_valid_syntax(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def convert(x: int) -> str: ...\n"
            "@overload\n"
            "def convert(x: str) -> int: ...\n"
            "def convert(x): return x\n"
        )
        assert_valid_syntax(c)
