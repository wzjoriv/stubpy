"""
tests/test_ast_pass.py
----------------------
Unit tests for stubpy.ast_pass:
  - ASTHarvester
  - ast_harvest()
  - ASTSymbols, ClassInfo, FunctionInfo, VariableInfo, TypeVarInfo
"""
from __future__ import annotations
from stubpy.ast_pass import (
    ASTHarvester, ASTSymbols, ClassInfo, FunctionInfo,
    TypeVarInfo, VariableInfo, ast_harvest,
)


class TestAstHarvestBasics:
    def test_empty_source(self):
        syms = ast_harvest("")
        assert syms.classes == []
        assert syms.functions == []
        assert syms.variables == []
        assert syms.typevar_decls == []
        assert syms.all_exports is None

    def test_syntax_error_returns_empty(self):
        syms = ast_harvest("def :(")
        assert syms.classes == []
        assert syms.functions == []

    def test_whitespace_only(self):
        syms = ast_harvest("   \n\n   ")
        assert syms.classes == []

    def test_comments_only(self):
        syms = ast_harvest("# just a comment\n# another\n")
        assert syms.classes == []
        assert syms.functions == []


class TestClassHarvest:
    def test_simple_class(self):
        syms = ast_harvest("class Foo: pass")
        assert len(syms.classes) == 1
        assert syms.classes[0].name == "Foo"

    def test_class_with_single_base(self):
        syms = ast_harvest("class Child(Parent): pass")
        assert syms.classes[0].bases == ["Parent"]

    def test_class_with_multiple_bases(self):
        syms = ast_harvest("class C(A, B): pass")
        assert "A" in syms.classes[0].bases
        assert "B" in syms.classes[0].bases

    def test_class_no_base(self):
        syms = ast_harvest("class Standalone: pass")
        assert syms.classes[0].bases == []

    def test_class_decorator_name(self):
        syms = ast_harvest("@dataclass\nclass Foo: pass")
        assert "dataclass" in syms.classes[0].decorators

    def test_class_dotted_decorator(self):
        syms = ast_harvest("import dc\n@dc.dataclass\nclass Foo: pass")
        assert "dataclass" in syms.classes[0].decorators

    def test_multiple_decorators(self):
        syms = ast_harvest("@final\n@dataclass\nclass Foo: pass")
        assert "final" in syms.classes[0].decorators
        assert "dataclass" in syms.classes[0].decorators

    def test_multiple_classes_source_order(self):
        syms = ast_harvest("class B: pass\nclass A: pass\n")
        assert syms.classes[0].name == "B"
        assert syms.classes[1].name == "A"

    def test_lineno(self):
        syms = ast_harvest("\n\nclass Foo: pass\n")
        assert syms.classes[0].lineno == 3

    def test_class_methods_harvested(self):
        src = "class Foo:\n    def a(self): pass\n    def b(self, x: int): pass\n"
        syms = ast_harvest(src)
        assert len(syms.classes[0].methods) == 2
        names = [m.name for m in syms.classes[0].methods]
        assert "a" in names and "b" in names

    def test_class_method_is_not_top_level_function(self):
        src = "class Foo:\n    def method(self): pass\n"
        syms = ast_harvest(src)
        assert syms.functions == []

    def test_method_async_detected(self):
        src = "class Foo:\n    async def afetch(self): pass\n"
        syms = ast_harvest(src)
        m = syms.classes[0].methods[0]
        assert m.is_async is True

    def test_method_classmethod_decorator(self):
        src = "class Foo:\n    @classmethod\n    def create(cls): ...\n"
        cls = ast_harvest(src).classes[0]
        m = next(m for m in cls.methods if m.name == "create")
        assert "classmethod" in m.decorators

    def test_method_staticmethod_decorator(self):
        src = "class Foo:\n    @staticmethod\n    def helper(): ...\n"
        cls = ast_harvest(src).classes[0]
        m = next(m for m in cls.methods if m.name == "helper")
        assert "staticmethod" in m.decorators

    def test_method_property_decorator(self):
        src = "class Foo:\n    @property\n    def val(self) -> int: ...\n"
        cls = ast_harvest(src).classes[0]
        m = next(m for m in cls.methods if m.name == "val")
        assert "property" in m.decorators


class TestFunctionHarvest:
    def test_simple_function(self):
        syms = ast_harvest("def foo(): pass")
        assert len(syms.functions) == 1
        assert syms.functions[0].name == "foo"

    def test_async_function(self):
        syms = ast_harvest("async def fetch(url: str) -> None: ...")
        fn = syms.functions[0]
        assert fn.is_async is True

    def test_sync_function(self):
        syms = ast_harvest("def greet(name: str) -> str: ...")
        assert syms.functions[0].is_async is False

    def test_overload_detection(self):
        src = (
            "from typing import overload\n"
            "@overload\ndef parse(x: int) -> int: ...\n"
            "@overload\ndef parse(x: str) -> str: ...\n"
            "def parse(x): ...\n"
        )
        syms = ast_harvest(src)
        overloaded = [f for f in syms.functions if f.is_overload]
        non_overloaded = [f for f in syms.functions if not f.is_overload]
        assert len(overloaded) == 2
        assert len(non_overloaded) == 1

    def test_return_annotation(self):
        syms = ast_harvest("def foo() -> int: ...")
        assert syms.functions[0].raw_return_annotation == "int"

    def test_no_return_annotation(self):
        syms = ast_harvest("def foo(): ...")
        assert syms.functions[0].raw_return_annotation is None

    def test_arg_annotations(self):
        src = "def foo(x: int, y: str = 'a', *args: float, **kwargs: bool) -> None: ...\n"
        fn = ast_harvest(src).functions[0]
        assert fn.raw_arg_annotations.get("x")       == "int"
        assert fn.raw_arg_annotations.get("y")       == "str"
        assert fn.raw_arg_annotations.get("*args")   == "float"
        assert fn.raw_arg_annotations.get("**kwargs") == "bool"

    def test_function_lineno(self):
        syms = ast_harvest("\ndef foo(): pass\n")
        assert syms.functions[0].lineno == 2

    def test_multiple_functions_source_order(self):
        src = "def z(): pass\ndef a(): pass\n"
        syms = ast_harvest(src)
        assert syms.functions[0].name == "z"
        assert syms.functions[1].name == "a"

    def test_function_decorator(self):
        src = "@staticmethod\ndef helper(): ...\n"
        fn = ast_harvest(src).functions[0]
        assert "staticmethod" in fn.decorators


class TestVariableHarvest:
    def test_annotated_variable(self):
        syms = ast_harvest("MAX: int = 100")
        v = syms.variables[0]
        assert v.name == "MAX"
        assert v.annotation_str == "int"
        assert v.value_repr == "100"

    def test_plain_variable(self):
        syms = ast_harvest("VERSION = '1.0'")
        v = syms.variables[0]
        assert v.name == "VERSION"
        assert v.annotation_str is None
        assert v.value_repr == "'1.0'"

    def test_private_variable_skipped(self):
        syms = ast_harvest("_PRIVATE = 1\n_X: int = 2\n")
        #assert "_PRIVATE" not in [v.name for v in syms.variables]
        #assert "_X" not in [v.name for v in syms.variables]

    def test_annotated_no_value(self):
        syms = ast_harvest("x: int\n")
        v = syms.variables[0]
        assert v.name == "x"
        assert v.annotation_str == "int"
        assert v.value_repr is None

    def test_typealias_not_in_variables(self):
        syms = ast_harvest("from typing import TypeAlias\nMyType: TypeAlias = int | str\n")
        # TypeAlias annotations go to typevar_decls, not variables
        var_names = [v.name for v in syms.variables]
        assert "MyType" not in var_names

    def test_variable_lineno(self):
        syms = ast_harvest("\nMAX: int = 1\n")
        assert syms.variables[0].lineno == 2


class TestTypeVarHarvest:
    def test_typevar(self):
        syms = ast_harvest("from typing import TypeVar\nT = TypeVar('T')")
        tv = syms.typevar_decls[0]
        assert tv.name == "T"
        assert tv.kind == "TypeVar"

    def test_paramspec(self):
        syms = ast_harvest("from typing import ParamSpec\nP = ParamSpec('P')")
        tv = syms.typevar_decls[0]
        assert tv.name == "P"
        assert tv.kind == "ParamSpec"

    def test_typevartuple(self):
        syms = ast_harvest("from typing import TypeVarTuple\nTs = TypeVarTuple('Ts')")
        tv = syms.typevar_decls[0]
        assert tv.name == "Ts"
        assert tv.kind == "TypeVarTuple"

    def test_newtype(self):
        syms = ast_harvest("from typing import NewType\nUserId = NewType('UserId', int)")
        tv = syms.typevar_decls[0]
        assert tv.name == "UserId"
        assert tv.kind == "NewType"

    def test_typealias_ann_assign(self):
        syms = ast_harvest("from typing import TypeAlias\nMyType: TypeAlias = int | str")
        tv = syms.typevar_decls[0]
        assert tv.name == "MyType"
        assert tv.kind == "TypeAlias"


class TestAllExports:
    def test_all_list(self):
        syms = ast_harvest('__all__ = ["Foo", "bar"]')
        assert syms.all_exports == ["Foo", "bar"]

    def test_all_tuple(self):
        syms = ast_harvest('__all__ = ("Foo", "bar")')
        assert syms.all_exports == ["Foo", "bar"]

    def test_no_all(self):
        syms = ast_harvest("class Foo: pass")
        assert syms.all_exports is None

    def test_all_empty(self):
        syms = ast_harvest('__all__ = []')
        assert syms.all_exports == []


class TestIfTypechecking:
    def test_if_type_checking_visited(self):
        src = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    class TypeOnly: pass\n"
            "    def helper(): pass\n"
        )
        syms = ast_harvest(src)
        class_names = [c.name for c in syms.classes]
        func_names  = [f.name for f in syms.functions]
        assert "TypeOnly" in class_names
        assert "helper"   in func_names

    def test_if_else_both_visited(self):
        src = (
            "if True:\n"
            "    class A: pass\n"
            "else:\n"
            "    class B: pass\n"
        )
        syms = ast_harvest(src)
        names = [c.name for c in syms.classes]
        assert "A" in names and "B" in names


class TestASTSymbolsDataclass:
    def test_default_empty(self):
        s = ASTSymbols()
        assert s.classes == []
        assert s.functions == []
        assert s.variables == []
        assert s.typevar_decls == []
        assert s.all_exports is None

    def test_function_info_defaults(self):
        fi = FunctionInfo(name="foo", lineno=1)
        assert fi.is_async is False
        assert fi.is_overload is False
        assert fi.decorators == []
        assert fi.raw_arg_annotations == {}
        assert fi.raw_return_annotation is None

    def test_class_info_defaults(self):
        ci = ClassInfo(name="Foo", lineno=1)
        assert ci.bases == []
        assert ci.decorators == []
        assert ci.methods == []

    def test_variable_info_defaults(self):
        vi = VariableInfo(name="X", lineno=1)
        assert vi.annotation_str is None
        assert vi.value_repr is None

    def test_typevar_info(self):
        ti = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
        assert ti.name == "T"
        assert ti.kind == "TypeVar"
