"""
tests/test_annotations.py
--------------------------
Unit tests for stubpy.annotations:
  - annotation_to_str  (via dispatch table)
  - default_to_str
  - format_param
"""
from __future__ import annotations

import inspect
import typing
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

import pytest

from stubpy.annotations import annotation_to_str, default_to_str, format_param
from stubpy.context import AliasEntry, StubContext


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


# ---------------------------------------------------------------------------
# annotation_to_str — sentinels
# ---------------------------------------------------------------------------

class TestAnnotationSentinels:
    def test_parameter_empty(self, ctx):
        assert annotation_to_str(inspect.Parameter.empty, ctx) == ""

    def test_signature_empty(self, ctx):
        assert annotation_to_str(inspect.Signature.empty, ctx) == ""


# ---------------------------------------------------------------------------
# annotation_to_str — plain types
# ---------------------------------------------------------------------------

class TestAnnotationPlainTypes:
    @pytest.mark.parametrize("typ,expected", [
        (int,   "int"),
        (str,   "str"),
        (float, "float"),
        (bool,  "bool"),
        (bytes, "bytes"),
    ])
    def test_builtin_types(self, ctx, typ, expected):
        assert annotation_to_str(typ, ctx) == expected

    def test_none_type(self, ctx):
        assert annotation_to_str(type(None), ctx) == "None"

    def test_user_class(self, ctx):
        class MyWidget: pass
        assert annotation_to_str(MyWidget, ctx) == "MyWidget"


# ---------------------------------------------------------------------------
# annotation_to_str — forward references
# ---------------------------------------------------------------------------

class TestAnnotationForwardRefs:
    def test_str_forward_ref(self, ctx):
        assert annotation_to_str("Element", ctx) == "Element"

    def test_str_forward_ref_with_quotes(self, ctx):
        assert annotation_to_str("'Element'", ctx) == "Element"

    def test_typing_forward_ref(self, ctx):
        ref = typing.ForwardRef("Container")
        assert annotation_to_str(ref, ctx) == "Container"


# ---------------------------------------------------------------------------
# annotation_to_str — PEP 604 unions
# ---------------------------------------------------------------------------

class TestAnnotationPep604:
    def test_optional(self, ctx):
        assert annotation_to_str(str | None, ctx) == "Optional[str]"

    def test_two_types(self, ctx):
        result = annotation_to_str(str | int, ctx)
        assert result == "str | int"

    def test_three_types(self, ctx):
        result = annotation_to_str(str | int | float, ctx)
        assert result == "str | int | float"

    def test_none_in_middle_is_optional(self, ctx):
        # Python normalises None to last in __args__ for | syntax
        result = annotation_to_str(str | None, ctx)
        assert result == "Optional[str]"


# ---------------------------------------------------------------------------
# annotation_to_str — typing generics
# ---------------------------------------------------------------------------

class TestAnnotationTypingGenerics:
    def test_optional(self, ctx):
        assert annotation_to_str(Optional[str], ctx) == "Optional[str]"

    def test_union_two_types(self, ctx):
        assert annotation_to_str(Union[str, int], ctx) == "Union[str, int]"

    def test_union_with_none(self, ctx):
        assert annotation_to_str(Union[str, None], ctx) == "Optional[str]"

    def test_union_three_types(self, ctx):
        result = annotation_to_str(Union[str, int, float], ctx)
        assert result == "Union[str, int, float]"

    def test_list(self, ctx):
        assert annotation_to_str(List[str], ctx) == "List[str]"

    def test_dict(self, ctx):
        assert annotation_to_str(Dict[str, int], ctx) == "Dict[str, int]"

    def test_tuple(self, ctx):
        assert annotation_to_str(Tuple[float, float], ctx) == "Tuple[float, float]"

    def test_sequence(self, ctx):
        assert annotation_to_str(Sequence[int], ctx) == "Sequence[int]"

    def test_nested_generic(self, ctx):
        ann = List[Tuple[str, int]]
        assert annotation_to_str(ann, ctx) == "List[Tuple[str, int]]"

    def test_callable_no_args(self, ctx):
        assert annotation_to_str(Callable[[], None], ctx) == "Callable[[], None]"

    def test_callable_with_args(self, ctx):
        result = annotation_to_str(Callable[[int, str], bool], ctx)
        assert result == "Callable[[int, str], bool]"

    def test_callable_optional(self, ctx):
        ann = Optional[Callable[[], None]]
        result = annotation_to_str(ann, ctx)
        assert result == "Optional[Callable[[], None]]"

    def test_literal_strings(self, ctx):
        ann = Literal["butt", "round"]
        assert annotation_to_str(ann, ctx) == "Literal['butt', 'round']"

    def test_literal_ints(self, ctx):
        ann = Literal[1, 2, 3]
        assert annotation_to_str(ann, ctx) == "Literal[1, 2, 3]"


# ---------------------------------------------------------------------------
# annotation_to_str — alias registry
# ---------------------------------------------------------------------------

class TestAnnotationAliasLookup:
    def test_alias_returned_instead_of_expansion(self, ctx):
        my_alias = str | float | int
        ctx.alias_registry.append(AliasEntry(my_alias, "types.Length"))
        ctx.type_module_imports["types"] = "from demo import types"
        result = annotation_to_str(my_alias, ctx)
        assert result == "types.Length"

    def test_alias_marks_module_as_used(self, ctx):
        my_alias = str | float | int
        ctx.alias_registry.append(AliasEntry(my_alias, "types.Length"))
        ctx.type_module_imports["types"] = "from demo import types"
        annotation_to_str(my_alias, ctx)
        assert "types" in ctx.used_type_imports

    def test_unregistered_annotation_not_aliased(self, ctx):
        ctx.alias_registry.append(AliasEntry(str | int, "types.MyType"))
        ctx.type_module_imports["types"] = "from demo import types"
        # str | float is a different object
        result = annotation_to_str(str | float, ctx)
        assert result != "types.MyType"


# ---------------------------------------------------------------------------
# default_to_str
# ---------------------------------------------------------------------------

class TestDefaultToStr:
    def test_empty_returns_empty_string(self):
        assert default_to_str(inspect.Parameter.empty) == ""

    @pytest.mark.parametrize("value,expected", [
        (None,    "None"),
        ("black", "'black'"),
        (10,      "10"),
        (1.0,     "1.0"),
        (True,    "True"),
        (False,   "False"),
        ([1, 2],  "[1, 2]"),
    ])
    def test_various_defaults(self, value, expected):
        assert default_to_str(value) == expected


# ---------------------------------------------------------------------------
# format_param
# ---------------------------------------------------------------------------

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
