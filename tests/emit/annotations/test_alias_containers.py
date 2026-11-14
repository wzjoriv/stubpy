"""Alias preservation inside generic containers."""
from __future__ import annotations

import typing

import pytest

import stubpy
from stubpy.config import Config
from stubpy.core.context import AliasEntry, StubContext
from stubpy.emit.annotations import annotation_to_str


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


def demo_types_color(ctx):
    """Helper: return Color from the first alias registry entry named types.Color."""
    from demo import types as dt
    return dt.Color


class TestAnnotationAliasContainerForms:
    """
    Tests for alias preservation when the alias appears inside a generic
    container (List, Dict, Optional, etc.) rather than as a bare annotation.

    These complement TestAnnotationAliasWithNone by verifying that the alias
    lookup works recursively for every argument position of a generic.

    Unfixable edge cases (documented as xfail):
    --------------------------------------------
    Python's ``typing.Union`` *flattens* nested unions at construction time.
    ``Union[Color, int]`` where ``Color = Union[str, Tuple[...]]`` produces
    ``Union[str, Tuple[...], int]`` — the Color boundary is permanently lost
    before stubpy ever sees the annotation.  There is no runtime information
    that would allow recovery of the original alias.  These cases are marked
    ``xfail`` to document the known limitation without hiding it.
    """

    @pytest.fixture
    def ctx(self):
        Color     = typing.Union[
            str,
            typing.Tuple[float, float, float],
            typing.Tuple[float, float, float, float],
        ]
        DashArray = typing.Union[str, typing.Sequence[typing.Union[int, float]]]
        c = StubContext()
        c.alias_registry.append(AliasEntry(Color,     "types.Color"))
        c.alias_registry.append(AliasEntry(DashArray, "types.DashArray"))
        c.type_module_imports["types"] = "from demo import types"
        return c, Color, DashArray

    def test_optional_alias_explicit(self, ctx):
        """typing.Optional[Color] → types.Color | None (modern)"""
        c, Color, _ = ctx
        result = annotation_to_str(typing.Optional[Color], c)
        assert result == "types.Color | None"

    def test_optional_alias_explicit_legacy(self, ctx):
        """typing.Optional[Color] → Optional[types.Color] (legacy)"""
        c_orig, Color, _ = ctx
        legacy = StubContext(config=Config(union_style="legacy"))
        legacy.alias_registry = c_orig.alias_registry[:]
        legacy.type_module_imports.update(c_orig.type_module_imports)
        assert annotation_to_str(typing.Optional[Color], legacy) == "Optional[types.Color]"

    def test_union_alias_none_explicit(self, ctx):
        """typing.Union[Color, None] → types.Color | None (modern)"""
        c, Color, _ = ctx
        result = annotation_to_str(typing.Union[Color, None], c)
        assert result == "types.Color | None"

    def test_union_alias_none_explicit_legacy(self, ctx):
        """typing.Union[Color, None] → Optional[types.Color] (legacy)"""
        c_orig, Color, _ = ctx
        legacy = StubContext(config=Config(union_style="legacy"))
        legacy.alias_registry = c_orig.alias_registry[:]
        legacy.type_module_imports.update(c_orig.type_module_imports)
        assert annotation_to_str(typing.Union[Color, None], legacy) == "Optional[types.Color]"

    def test_optional_dasharray(self, ctx):
        """typing.Optional[DashArray] → types.DashArray | None (modern)"""
        c, _, DashArray = ctx
        result = annotation_to_str(typing.Optional[DashArray], c)
        assert result == "types.DashArray | None"

    def test_list_of_alias(self, ctx):
        """List[Color] → List[types.Color]"""
        c, Color, _ = ctx
        assert annotation_to_str(typing.List[Color], c) == "List[types.Color]"

    def test_optional_list_of_alias(self, ctx):
        """Optional[List[Color]] → List[types.Color] | None (modern)"""
        c, Color, _ = ctx
        result = annotation_to_str(typing.Optional[typing.List[Color]], c)
        assert result == "List[types.Color] | None"

    def test_dict_value_alias(self, ctx):
        """Dict[str, Color] → Dict[str, types.Color]"""
        c, Color, _ = ctx
        assert annotation_to_str(typing.Dict[str, Color], c) == "Dict[str, types.Color]"

    def test_dict_both_aliases(self, ctx):
        """Dict[Color, DashArray] → Dict[types.Color, types.DashArray]"""
        c, Color, DashArray = ctx
        result = annotation_to_str(typing.Dict[Color, DashArray], c)
        assert result == "Dict[types.Color, types.DashArray]"

    def test_sequence_of_alias(self, ctx):
        """Sequence[Color] → Sequence[types.Color]"""
        c, Color, _ = ctx
        assert annotation_to_str(typing.Sequence[Color], c) == "Sequence[types.Color]"

    def test_tuple_with_alias(self, ctx):
        """Tuple[Color, float] → Tuple[types.Color, float]"""
        c, Color, _ = ctx
        assert annotation_to_str(typing.Tuple[Color, float], c) == "Tuple[types.Color, float]"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Python's typing.Union flattens nested unions at construction time. "
            "Union[Color, int] where Color=Union[str,Tuple[...]] becomes "
            "Union[str, Tuple[...], int]. The Color boundary is permanently lost; "
            "stubpy cannot recover it."
        ),
    )
    def test_union_alias_plus_other_type_unfixable(self, ctx):
        """Union[Color, int, None] cannot preserve the alias — Python flattens."""
        c, Color, _ = ctx
        result = annotation_to_str(typing.Union[Color, int, None], c)
        assert "types.Color" in result

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Union of two multi-type aliases is also flattened by Python. "
            "Union[Color, DashArray] loses both alias boundaries."
        ),
    )
    def test_union_of_two_aliases_unfixable(self, ctx):
        """Union[Color, DashArray] cannot preserve either alias — Python flattens."""
        c, Color, DashArray = ctx
        result = annotation_to_str(typing.Union[Color, DashArray], c)
        assert "types.Color" in result and "types.DashArray" in result

    def test_optional_alias_in_generated_stub(self, demo_dir, tmp_path):
        """
        When a developer writes ``Optional[types.Color]`` explicitly in source
        (rather than ``types.Color | None``), the stub must still emit
        ``Optional[types.Color]``.
        """
        src = (
            "from __future__ import annotations\n"
            "from typing import Optional\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass Widget(Element):\n"
            "    def __init__(self, stroke: Optional[types.Color] = None,\n"
            "                 clip: Optional[str] = None, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        tmp = tmp_path / "widget.py"
        tmp.write_text(src, encoding="utf-8")
        content = stubpy.render(str(tmp)).text
        widget_sec = content.split("class Widget")[1]
        assert "Optional[types.Color]" in widget_sec, (
            f"Expected Optional[types.Color] in stub:\n{widget_sec}"
        )
        assert "Union[str, Tuple" not in widget_sec


class TestTupleListAliasForms:
    """
    Tests for alias preservation inside tuple and list generic forms.

    Covers both PEP 585 lowercase builtins (``tuple``, ``list``) and
    the legacy ``typing.Tuple`` / ``typing.List`` uppercase forms.
    """

    @pytest.fixture
    def ctx(self, empty_ctx):
        from demo import types as demo_types
        empty_ctx.alias_registry.append(AliasEntry(demo_types.Color,  "types.Color"))
        empty_ctx.alias_registry.append(AliasEntry(demo_types.Length, "types.Length"))
        empty_ctx.alias_registry.append(AliasEntry(demo_types.Number, "types.Number"))
        empty_ctx.type_module_imports["types"] = "from demo import types"
        return empty_ctx

    def test_list_alias(self, ctx):
        assert annotation_to_str(list[demo_types_color(ctx)], ctx) == "list[types.Color]"

    def test_List_alias(self, ctx):
        from demo import types as dt
        assert annotation_to_str(typing.List[dt.Color], ctx) == "List[types.Color]"

    def test_tuple_two_aliases_lowercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[dt.Color, dt.Color], ctx)
        assert result == "tuple[types.Color, types.Color]"

    def test_Tuple_two_aliases_uppercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(typing.Tuple[dt.Color, dt.Color], ctx)
        assert result == "Tuple[types.Color, types.Color]"

    def test_tuple_three_aliases_lowercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[dt.Color, dt.Color, dt.Length], ctx)
        assert result == "tuple[types.Color, types.Color, types.Length]"

    def test_Tuple_three_aliases_uppercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(typing.Tuple[dt.Color, dt.Color, dt.Length], ctx)
        assert result == "Tuple[types.Color, types.Color, types.Length]"

    def test_tuple_alias_and_plain_lowercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[dt.Color, int, float], ctx)
        assert result == "tuple[types.Color, int, float]"

    def test_Tuple_alias_and_plain_uppercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(typing.Tuple[dt.Color, int, float], ctx)
        assert result == "Tuple[types.Color, int, float]"

    def test_tuple_variadic_alias_lowercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[dt.Length, ...], ctx)
        assert result == "tuple[types.Length, ...]"
        assert "Ellipsis" not in result

    def test_Tuple_variadic_alias_uppercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(typing.Tuple[dt.Length, ...], ctx)
        assert result == "Tuple[types.Length, ...]"
        assert "Ellipsis" not in result

    def test_tuple_variadic_no_alias(self, ctx):
        result = annotation_to_str(typing.Tuple[int, ...], ctx)
        assert result == "Tuple[int, ...]"

    def test_list_of_tuple_with_aliases(self, ctx):
        from demo import types as dt
        result = annotation_to_str(list[tuple[dt.Color, dt.Length]], ctx)
        assert result == "list[tuple[types.Color, types.Length]]"

    def test_tuple_of_list_with_alias(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[list[dt.Color], dt.Length], ctx)
        assert result == "tuple[list[types.Color], types.Length]"
