"""
tests/test_ast_pass.py
----------------------
Unit tests for stubpy.ast_pass:
  - ASTHarvester
  - ast_harvest()
  - ASTSymbols, ClassInfo, FunctionInfo, VariableInfo, TypeVarInfo
"""
from __future__ import annotations
import pytest
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
        # The harvester is a pure collector — it gathers every variable so
        # the symbol table can apply its own filtering policy (include_private).
        syms = ast_harvest("_PRIVATE = 1\n_X: int = 2\nPUBLIC = 3\n")
        names = [v.name for v in syms.variables]
        # All names are harvested, including private ones
        assert "_PRIVATE" in names
        assert "_X" in names
        assert "PUBLIC" in names
        # Symbol-table filtering is tested separately in test_module_symbols.py

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


# ---------------------------------------------------------------------------
# # stubpy: ignore directive
# ---------------------------------------------------------------------------

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
        # After a class definition it is NOT honoured
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


# ---------------------------------------------------------------------------
# Implicit TypeAlias detection (bare assignment)
# ---------------------------------------------------------------------------

class TestImplicitTypeAliasDetection:
    """Bare assignments that look like type aliases are harvested as TypeVarInfo."""

    def test_pep604_union(self):
        syms = ast_harvest("Number = int | float\n")
        assert len(syms.typevar_decls) == 1
        assert syms.typevar_decls[0].name == "Number"
        assert syms.typevar_decls[0].kind == "TypeAlias"
        assert "int | float" in syms.typevar_decls[0].source_str

    def test_subscripted_union(self):
        syms = ast_harvest("from typing import Union\nLength = Union[str, float, int]\n")
        assert any(d.name == "Length" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_subscripted_list(self):
        syms = ast_harvest("Items = list[int]\n")
        assert any(d.name == "Items" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_bare_builtin_type_name(self):
        syms = ast_harvest("MyStr = str\n")
        assert any(d.name == "MyStr" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_bare_int(self):
        syms = ast_harvest("Count = int\n")
        assert any(d.name == "Count" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_bare_list(self):
        syms = ast_harvest("MyList = list\n")
        assert any(d.name == "MyList" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_constant_not_alias(self):
        syms = ast_harvest("VERSION = '1.0.0'\n")
        assert not any(d.kind == "TypeAlias" for d in syms.typevar_decls)
        assert any(v.name == "VERSION" for v in syms.variables)

    def test_integer_constant_not_alias(self):
        syms = ast_harvest("PORT = 8080\n")
        assert not any(d.kind == "TypeAlias" for d in syms.typevar_decls)
        assert any(v.name == "PORT" for v in syms.variables)

    def test_arbitrary_name_not_alias(self):
        # SomeArbitraryClass is not a known type name → not treated as alias
        syms = ast_harvest("MyAlias = SomeArbitraryClass\n")
        assert not any(d.kind == "TypeAlias" for d in syms.typevar_decls)
        assert any(v.name == "MyAlias" for v in syms.variables)

    def test_explicit_typealias_annotation_still_works(self):
        syms = ast_harvest("from typing import TypeAlias\nColor: TypeAlias = str\n")
        assert any(d.name == "Color" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_not_duplicated_with_variables(self):
        syms = ast_harvest("Number = int | float\n")
        assert not any(v.name == "Number" for v in syms.variables)


# ---------------------------------------------------------------------------
# Python 3.12+ PEP 695 type statement
# ---------------------------------------------------------------------------

class TestPEP695TypeStatement:
    """Python 3.12+ ``type Name = ...`` soft-keyword is harvested correctly."""

    def test_simple_type_alias(self):
        import sys
        if sys.version_info < (3, 12):
            pytest.skip("PEP 695 requires Python 3.12+")
        syms = ast_harvest("type Vector = list[float]\n")
        assert any(d.name == "Vector" and d.kind == "TypeAlias" for d in syms.typevar_decls)

    def test_generic_type_alias(self):
        import sys
        if sys.version_info < (3, 12):
            pytest.skip("PEP 695 requires Python 3.12+")
        syms = ast_harvest("type Stack[T] = list[T]\n")
        d = next((d for d in syms.typevar_decls if d.name == "Stack"), None)
        assert d is not None
        assert d.kind == "TypeAlias"
        assert "list[T]" in d.source_str

    def test_source_str_is_rhs(self):
        import sys
        if sys.version_info < (3, 12):
            pytest.skip("PEP 695 requires Python 3.12+")
        syms = ast_harvest("type MyNum = int | float\n")
        d = next(d for d in syms.typevar_decls if d.name == "MyNum")
        assert "int | float" in d.source_str


# ===========================================================================
# infer_type_from_literal — new utility (v0.6.1)
# ===========================================================================

class TestInferTypeFromLiteral:
    """Unit tests for :func:`~stubpy.ast_pass.infer_type_from_literal`."""

    def _infer(self, expr: str):
        import ast
        from stubpy.ast_pass import infer_type_from_literal
        return infer_type_from_literal(ast.parse(expr, mode="eval").body)

    def test_int(self):       assert self._infer("42")    == "int"
    def test_float(self):     assert self._infer("3.14")  == "float"
    def test_str(self):       assert self._infer('"hi"')  == "str"
    def test_bool_true(self): assert self._infer("True")  == "bool"
    def test_bool_false(self):assert self._infer("False") == "bool"
    def test_none(self):      assert self._infer("None")  == "None"
    def test_bytes(self):     assert self._infer("b'x'")  == "bytes"
    def test_negative_int(self):   assert self._infer("-42")   == "int"
    def test_negative_float(self): assert self._infer("-3.14") == "float"

    def test_bool_before_int(self):
        """bool must return 'bool', not 'int' (bool is a subtype of int)."""
        assert self._infer("True") == "bool"
        assert self._infer("False") == "bool"

    def test_homogeneous_list(self):
        assert self._infer("[1, 2, 3]") == "list[int]"
        assert self._infer('["a", "b"]') == "list[str]"

    def test_empty_list(self):      assert self._infer("[]") == "list"
    def test_heterogeneous_list(self): assert self._infer("[1, 'x']") == "list"

    def test_homogeneous_tuple(self):
        assert self._infer("(1, 2)") == "tuple[int, int]"
        assert self._infer('(1, "x")') == "tuple[int, str]"

    def test_empty_tuple(self):    assert self._infer("()") == "tuple[()]"

    def test_homogeneous_set(self):
        assert self._infer("{1, 2}") == "set[int]"

    def test_typed_dict(self):
        assert self._infer('{"a": 1}') == "dict[str, int]"

    def test_empty_dict(self):      assert self._infer("{}") == "dict"
    def test_heterogeneous_dict(self): assert self._infer('{"a": 1, "b": "x"}') == "dict"

    def test_variable_returns_none(self):
        assert self._infer("some_var") is None

    def test_function_call_returns_none(self):
        assert self._infer("int()") is None

    def test_complex_literal(self):
        assert self._infer("2j") == "complex"



    def test_unary_minus_int(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("-42", mode="eval").body
        assert infer_type_from_literal(node) == "int"

    def test_unary_minus_float(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("-3.14", mode="eval").body
        assert infer_type_from_literal(node) == "float"

    def test_complex_via_binop(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("1+2j", mode="eval").body
        assert infer_type_from_literal(node) == "complex"

    def test_complex_pure_imaginary(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("2j", mode="eval").body
        assert infer_type_from_literal(node) == "complex"

    def test_ellipsis_yields_any(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("...", mode="eval").body
        assert infer_type_from_literal(node) == "Any"

    def test_empty_tuple(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("()", mode="eval").body
        result = infer_type_from_literal(node)
        assert result in ("tuple[()]", "tuple")

    def test_variable_reference_returns_none(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("os.sep", mode="eval").body
        assert infer_type_from_literal(node) is None

    def test_function_call_returns_none(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("list()", mode="eval").body
        assert infer_type_from_literal(node) is None

    def test_heterogeneous_list_returns_bare_list(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse("[1, 'a', True]", mode="eval").body
        assert infer_type_from_literal(node) == "list"

    def test_heterogeneous_dict_returns_bare_dict(self):
        from stubpy.ast_pass import infer_type_from_literal
        import ast as _ast
        node = _ast.parse('{"a": 1, "b": "x"}', mode="eval").body
        # values are mixed (int, str) → bare dict
        assert infer_type_from_literal(node) == "dict"

class TestRawParamHarvesting:
    """FunctionInfo.raw_params is populated correctly by the AST harvester."""

    def test_simple_function_params(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x: int, y: str = "hi", z=3.14) -> bool: ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert len(fn.raw_params) == 3
        names = [p.name for p in fn.raw_params]
        assert names == ["x", "y", "z"]

    def test_param_annotations_captured(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x: int, y: str = "hi") -> bool: ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_params[0].annotation_str == "int"
        assert fn.raw_params[1].annotation_str == "str"

    def test_default_repr_captured(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x: int = 0, y: str = "hi"): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_params[0].default_repr == "0"
        assert fn.raw_params[1].default_repr in ('"hi"', "'hi'")

    def test_inferred_type_from_literal_default(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x=42, y="hello", z=True): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        inferred = {p.name: p.inferred_type_str for p in fn.raw_params}
        assert inferred["x"] == "int"
        assert inferred["y"] == "str"
        assert inferred["z"] == "bool"

    def test_param_kinds_preserved(self):
        from stubpy.ast_pass import ast_harvest
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
        from stubpy.ast_pass import ast_harvest
        src = 'def f(*args: str, **kwargs: int): ...'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        kinds = {p.name: p.kind for p in fn.raw_params}
        assert kinds["args"] == "VAR_POSITIONAL"
        assert kinds["kwargs"] == "VAR_KEYWORD"
        assert fn.raw_params[0].annotation_str == "str"

    def test_variable_inferred_from_literal(self):
        from stubpy.ast_pass import ast_harvest
        src = 'X = 100\nLABEL = "hello"\nFLAG = True\nRATIO = 3.14\n'
        syms = ast_harvest(src)
        inferred = {v.name: v.inferred_type_str for v in syms.variables}
        assert inferred["X"] == "int"
        assert inferred["LABEL"] == "str"
        assert inferred["FLAG"] == "bool"
        assert inferred["RATIO"] == "float"

    def test_return_type_inferred_from_literal(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x):\n    return True\n'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_inferred_return == "bool"

    def test_mixed_returns_union(self):
        from stubpy.ast_pass import ast_harvest
        src = 'def f(x):\n    if x:\n        return 1\n    return "hello"\n'
        syms = ast_harvest(src)
        fn = syms.functions[0]
        assert fn.raw_inferred_return is not None
        assert "int" in fn.raw_inferred_return
        assert "str" in fn.raw_inferred_return


class TestASTOnlyModeQuality:
    """AST-only mode produces rich stubs with type inference from defaults."""

    def _ast_stub(self, src: str) -> str:
        import textwrap, tempfile
        from pathlib import Path
        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext, ExecutionMode
        src = textwrap.dedent(src)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = Path(f.name)
        try:
            ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
            return generate_stub(str(tmp), str(tmp.with_suffix(".pyi")), ctx=ctx)
        finally:
            tmp.unlink(missing_ok=True)
            tmp.with_suffix(".pyi").unlink(missing_ok=True)

    def test_module_variable_type_from_literal(self):
        stub = self._ast_stub("MAX = 100\nLABEL = 'hi'\nFLAG = True\n")
        assert "MAX: int" in stub
        assert "LABEL: str" in stub
        assert "FLAG: bool" in stub

    def test_function_params_present_in_ast_only(self):
        stub = self._ast_stub("def f(x=0, y='hi', z=True): ...\n")
        assert "def f(" in stub
        # Inferred types now appear as real annotations (x: int = 0)
        assert "x: int = 0" in stub
        assert "z: bool = True" in stub

    def test_inferred_types_for_unannotated_params_from_defaults(self):
        """Literal defaults produce real type annotations, not # type: comments."""
        stub = self._ast_stub("def f(x=0, y='hi', active=True): ...\n")
        # Inferred from literal defaults → real annotations (not # type: comments)
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub
        # No bare comment-only types
        assert "# type:" not in stub

    def test_explicit_annotations_respected(self):
        stub = self._ast_stub("def f(x: int, y: str = 'hi'): ...\n")
        assert "x: int" in stub
        assert "y: str = 'hi'" in stub
        # No # type: comments for annotated params
        fn_part = stub.split("def f(")[1]
        assert "# type:" not in fn_part

    def test_return_annotation_preserved(self):
        stub = self._ast_stub("def f() -> bool: ...\n")
        assert "-> bool" in stub

    def test_class_method_params_in_ast_only(self):
        stub = self._ast_stub(
            "class Widget:\n"
            "    def __init__(self, x=0, y='text', active=True):\n"
            "        pass\n"
        )
        assert "def __init__" in stub
        # Inferred from literal defaults → real annotations
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub

    def test_ast_only_stub_is_valid_syntax(self):
        from tests.conftest import assert_valid_syntax
        stub = self._ast_stub(
            "X = 100\nY = 'hi'\n\n"
            "def f(a=1, b='x', c=True, *args, d=3.14, **kw): ...\n\n"
            "class C:\n"
            "    def m(self, x=0, y='text'): pass\n"
        )
        assert_valid_syntax(stub)

    def test_positional_only_and_kw_only_in_ast_only(self):
        stub = self._ast_stub(
            "def f(x: int, y=1.0, /, z: str = 'hi', *, debug=False): ...\n"
        )
        assert "x: int" in stub
        assert "y: float" in stub         # inferred as real annotation
        assert "z: str = 'hi'" in stub
        assert "debug: bool" in stub      # inferred as real annotation
