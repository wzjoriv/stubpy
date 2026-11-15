"""Tests for the built-in annotation handlers."""
from __future__ import annotations

import inspect
import typing
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

import pytest

from stubpy.config import Config
from stubpy.core.context import AliasEntry, StubContext
from stubpy.emit.annotations import annotation_to_str
from tests.conftest import _ctx, _generate


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


@pytest.fixture
def legacy_ctx() -> StubContext:
    """StubContext with union_style='legacy' for Optional/Union output."""
    from stubpy.config import Config
    return StubContext(config=Config(union_style="legacy"))


class TestAnnotationSentinels:
    def test_parameter_empty(self, ctx):
        assert annotation_to_str(inspect.Parameter.empty, ctx) == ""

    def test_signature_empty(self, ctx):
        assert annotation_to_str(inspect.Signature.empty, ctx) == ""


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


class TestAnnotationForwardRefs:
    def test_str_forward_ref(self, ctx):
        assert annotation_to_str("Element", ctx) == "Element"

    def test_str_forward_ref_with_quotes(self, ctx):
        assert annotation_to_str("'Element'", ctx) == "Element"

    def test_typing_forward_ref(self, ctx):
        ref = typing.ForwardRef("Container")
        assert annotation_to_str(ref, ctx) == "Container"


class TestAnnotationPep604:
    def test_optional(self, ctx):
        assert annotation_to_str(str | None, ctx) == "str | None"

    def test_optional_legacy(self, legacy_ctx):
        assert annotation_to_str(str | None, legacy_ctx) == "Optional[str]"

    def test_two_types(self, ctx):
        result = annotation_to_str(str | int, ctx)
        assert result == "str | int"

    def test_three_types(self, ctx):
        result = annotation_to_str(str | int | float, ctx)
        assert result == "str | int | float"

    def test_none_in_middle_is_optional(self, ctx):
        result = annotation_to_str(str | None, ctx)
        assert result == "str | None"


class TestAnnotationTypingGenerics:
    def test_optional(self, ctx):
        assert annotation_to_str(Optional[str], ctx) == "str | None"

    def test_optional_legacy(self, legacy_ctx):
        assert annotation_to_str(Optional[str], legacy_ctx) == "Optional[str]"

    def test_union_two_types(self, ctx):
        assert annotation_to_str(Union[str, int], ctx) == "str | int"

    def test_union_two_types_legacy(self, legacy_ctx):
        assert annotation_to_str(Union[str, int], legacy_ctx) == "Union[str, int]"

    def test_union_with_none(self, ctx):
        assert annotation_to_str(Union[str, None], ctx) == "str | None"

    def test_union_with_none_legacy(self, legacy_ctx):
        assert annotation_to_str(Union[str, None], legacy_ctx) == "Optional[str]"

    def test_union_three_types(self, ctx):
        result = annotation_to_str(Union[str, int, float], ctx)
        assert result == "str | int | float"

    def test_union_three_types_legacy(self, legacy_ctx):
        result = annotation_to_str(Union[str, int, float], legacy_ctx)
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
        assert result == "Callable[[], None] | None"

    def test_callable_optional_legacy(self, legacy_ctx):
        ann = Optional[Callable[[], None]]
        result = annotation_to_str(ann, legacy_ctx)
        assert result == "Optional[Callable[[], None]]"

    def test_literal_strings(self, ctx):
        ann = Literal["butt", "round"]
        assert annotation_to_str(ann, ctx) == "Literal['butt', 'round']"

    def test_literal_ints(self, ctx):
        ann = Literal[1, 2, 3]
        assert annotation_to_str(ann, ctx) == "Literal[1, 2, 3]"


class TestAnnotationAliasLookup:
    def test_alias_returned_instead_of_expansion(self, ctx):
        my_alias = str | float | int
        ctx.alias_registry.append(AliasEntry(my_alias, "types.Length"))
        ctx.type_module_imports["types"] = "from drawkit import types"
        result = annotation_to_str(my_alias, ctx)
        assert result == "types.Length"

    def test_alias_marks_module_as_used(self, ctx):
        my_alias = str | float | int
        ctx.alias_registry.append(AliasEntry(my_alias, "types.Length"))
        ctx.type_module_imports["types"] = "from drawkit import types"
        annotation_to_str(my_alias, ctx)
        assert "types" in ctx.used_type_imports

    def test_unregistered_annotation_not_aliased(self, ctx):
        ctx.alias_registry.append(AliasEntry(str | int, "types.MyType"))
        ctx.type_module_imports["types"] = "from drawkit import types"
        result = annotation_to_str(str | float, ctx)
        assert result != "types.MyType"


class TestEllipsisAnnotation:
    """
    Tests for the ``...`` (Ellipsis) singleton rendering fix.

    Before the fix, ``annotation_to_str(...)`` fell through to the
    ``str(...)`` fallback which returns ``"Ellipsis"`` instead of ``"..."``.
    This produced broken stubs like ``Tuple[int, Ellipsis]`` instead of
    the correct ``Tuple[int, ...]``.
    """

    def test_ellipsis_singleton_renders_as_dots(self, ctx):
        """``...`` must render as ``'...'``, not ``'Ellipsis'``."""
        assert annotation_to_str(..., ctx) == "..."

    def test_ellipsis_not_rendered_as_class_name(self, ctx):
        """The old fallback produced ``'Ellipsis'`` — that must never appear."""
        result = annotation_to_str(..., ctx)
        assert result != "Ellipsis"
        assert result != "<class 'ellipsis'>"

    def test_typing_tuple_variadic_uppercase(self, ctx):
        """``Tuple[int, ...]`` must render with ``...`` not ``Ellipsis``."""
        result = annotation_to_str(typing.Tuple[int, ...], ctx)
        assert result == "Tuple[int, ...]"
        assert "Ellipsis" not in result

    def test_builtin_tuple_variadic_lowercase(self, ctx):
        """``tuple[int, ...]`` (PEP 585) must also render correctly."""
        result = annotation_to_str(tuple[int, ...], ctx)
        assert result == "tuple[int, ...]"
        assert "Ellipsis" not in result

    def test_typing_tuple_variadic_with_alias(self, empty_ctx):
        """``Tuple[types.Length, ...]`` preserves the alias AND uses ``...``."""
        ctx = empty_ctx
        length = typing.Union[str, float, int]
        ctx.alias_registry.append(AliasEntry(length, "types.Length"))
        ctx.type_module_imports["types"] = "from drawkit import types"
        result = annotation_to_str(typing.Tuple[length, ...], ctx)
        assert result == "Tuple[types.Length, ...]"
        assert "Ellipsis" not in result

    def test_builtin_tuple_variadic_with_alias(self, empty_ctx):
        """``tuple[types.Length, ...]`` (PEP 585) also works."""
        ctx = empty_ctx
        length = typing.Union[str, float, int]
        ctx.alias_registry.append(AliasEntry(length, "types.Length"))
        ctx.type_module_imports["types"] = "from drawkit import types"
        result = annotation_to_str(tuple[length, ...], ctx)
        assert result == "tuple[types.Length, ...]"
        assert "Ellipsis" not in result


class TestAnnotationTypeVar:
    """TypeVar objects render as their bare name, not ``~Name`` (Python 3.12+)."""

    def test_typevar_renders_as_name(self, empty_ctx):
        import typing
        T = typing.TypeVar("T")
        assert annotation_to_str(T, empty_ctx) == "T"

    def test_typevar_with_suffix_not_tilde(self, empty_ctx):
        import typing
        AnyStr = typing.TypeVar("AnyStr", str, bytes)
        result = annotation_to_str(AnyStr, empty_ctx)
        assert result == "AnyStr"
        assert "~" not in result

    def test_paramspec_renders_as_name(self, empty_ctx):
        import typing
        P = typing.ParamSpec("P")
        result = annotation_to_str(P, empty_ctx)
        assert result == "P"
        assert "~" not in result

    @pytest.mark.skipif(
        not hasattr(typing, "TypeVarTuple"),
        reason="typing.TypeVarTuple requires Python 3.11+"
    )
    def test_typevartuple_renders_as_name(self, empty_ctx):
        Ts = typing.TypeVarTuple("Ts")
        result = annotation_to_str(Ts, empty_ctx)
        assert result == "Ts"
        assert "~" not in result

    def test_generic_subscript_uses_typevar_name(self, empty_ctx):
        """Generic[T] renders the TypeVar name, not ~T."""
        import typing
        T = typing.TypeVar("T")

        class Box(typing.Generic[T]):
            pass

        b = Box.__orig_bases__[0]
        result = annotation_to_str(b, empty_ctx)
        assert "T" in result
        assert "~" not in result


class TestUnionStyleRename:
    def test_default_is_modern(self):
        cfg = Config()
        assert cfg.union_style == "modern"

    def test_modern_emits_pep604(self):
        ctx = _ctx(union_style="modern")
        result = annotation_to_str(int | None, ctx)
        assert result == "int | None"

    def test_legacy_emits_optional(self):
        ctx = _ctx(union_style="legacy")
        result = annotation_to_str(int | None, ctx)
        assert result == "Optional[int]"

    def test_legacy_union_three_types(self):
        ctx = _ctx(union_style="legacy")
        import typing
        result = annotation_to_str(typing.Union[int, str, float], ctx)
        assert "Union" in result

    def test_union_style_in_generated_stub(self):
        stub = _generate(
            """
            def f(x: int | None) -> str | None: ...
            """,
            union_style="legacy",
        )
        assert "Optional" in stub

    def test_union_style_modern_in_generated_stub(self):
        stub = _generate(
            """
            def f(x: int | None) -> str | None: ...
            """,
            union_style="modern",
        )
        assert "| None" in stub


class TestPython310Compat:
    """These tests run on all Python versions but specifically guard the
    behaviour that failed on Python 3.10."""

    def test_builtin_list_subscript(self):
        ctx = _ctx()
        assert annotation_to_str(list[int], ctx) == "list[int]"

    def test_builtin_tuple_subscript(self):
        ctx = _ctx()
        assert annotation_to_str(tuple[int, str], ctx) == "tuple[int, str]"

    def test_builtin_tuple_variadic(self):
        ctx = _ctx()
        assert annotation_to_str(tuple[int, ...], ctx) == "tuple[int, ...]"

    def test_builtin_dict_subscript(self):
        ctx = _ctx()
        assert annotation_to_str(dict[str, int], ctx) == "dict[str, int]"

    def test_builtin_tuple_with_alias(self):
        ctx = _ctx()
        MyT = type("MyT", (), {})
        ctx.alias_registry.append(AliasEntry(MyT, "mymod.MyT"))
        ctx.type_module_imports["mymod"] = "import mymod"
        result = annotation_to_str(tuple[MyT, int], ctx)
        assert "mymod.MyT" in result
        assert "int" in result

    def test_nested_builtin_generics(self):
        ctx = _ctx()
        result = annotation_to_str(list[tuple[int, str]], ctx)
        assert result == "list[tuple[int, str]]"

    def test_union_type_guard_does_not_crash(self):
        """Importing annotations does not crash regardless of Python version.

        On Python 3.10+ ``types.UnionType`` exists; on older versions the
        guard sets ``_UnionType = None`` so the predicate short-circuits
        safely.  Either way the module must import and ``annotation_to_str``
        must work.
        """
        from stubpy.core.context import StubContext
        from stubpy.emit.annotations import annotation_to_str
        from stubpy.emit.annotations.handlers import _UnionType
        assert _UnionType is not None
        assert annotation_to_str(int, StubContext()) == "int"
