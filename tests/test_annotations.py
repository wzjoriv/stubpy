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


@pytest.fixture
def legacy_ctx() -> StubContext:
    """StubContext with typing_style='legacy' for Optional/Union output."""
    from stubpy.context import StubConfig
    return StubContext(config=StubConfig(typing_style="legacy"))


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
        # Modern default: str | None (not Optional[str])
        assert annotation_to_str(str | None, ctx) == "str | None"

    def test_optional_legacy(self, legacy_ctx):
        # Legacy style preserves Optional[str]
        assert annotation_to_str(str | None, legacy_ctx) == "Optional[str]"

    def test_two_types(self, ctx):
        result = annotation_to_str(str | int, ctx)
        assert result == "str | int"

    def test_three_types(self, ctx):
        result = annotation_to_str(str | int | float, ctx)
        assert result == "str | int | float"

    def test_none_in_middle_is_optional(self, ctx):
        # Python normalises None to last in __args__ for | syntax
        # Modern style: just emit X | None
        result = annotation_to_str(str | None, ctx)
        assert result == "str | None"


# ---------------------------------------------------------------------------
# annotation_to_str — typing generics
# ---------------------------------------------------------------------------

class TestAnnotationTypingGenerics:
    def test_optional(self, ctx):
        # typing.Optional[str] = Union[str, None] → modern: str | None
        assert annotation_to_str(Optional[str], ctx) == "str | None"

    def test_optional_legacy(self, legacy_ctx):
        assert annotation_to_str(Optional[str], legacy_ctx) == "Optional[str]"

    def test_union_two_types(self, ctx):
        # Union[str, int] — no None, emitted as str | int in modern mode too
        assert annotation_to_str(Union[str, int], ctx) == "str | int"

    def test_union_two_types_legacy(self, legacy_ctx):
        assert annotation_to_str(Union[str, int], legacy_ctx) == "Union[str, int]"

    def test_union_with_none(self, ctx):
        # Modern: str | None
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
        # Optional[Callable[[], None]] = Union[Callable[[], None], None]
        # Modern: Callable[[], None] | None
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


# ---------------------------------------------------------------------------
# Alias preservation with | None (union-alias regression tests)
# ---------------------------------------------------------------------------

class TestAnnotationAliasWithNone:
    """
    Regression tests for the bug where a multi-type alias used as ``Alias | None``
    would be expanded to its raw constituent types instead of emitting
    ``Optional[types.Alias]``.

    Root cause: the alias registry held ``Color`` (= ``Union[str, Tuple[...]]``),
    but ``Color | None`` is a *different* Union object whose args are
    ``(str, Tuple[...], NoneType)``.  The alias lookup on the full annotation
    failed because the registry entry didn't include ``NoneType``.

    Fix: in both ``_handle_generic`` (typing.Union branch) and
    ``_handle_pep604_union``, reconstruct the non-None part of the union and
    check the alias registry on that before falling back to per-arg expansion.
    """

    @pytest.fixture
    def ctx_with_aliases(self):
        """StubContext pre-loaded with multi-type aliases matching demo/types.py."""
        import typing
        ctx = StubContext()
        # Color = Union[str, Tuple[float, float, float], Tuple[float, float, float, float]]
        Color = typing.Union[
            str,
            typing.Tuple[float, float, float],
            typing.Tuple[float, float, float, float],
        ]
        # DashArray = Union[str, Sequence[Union[int, float]]]
        DashArray = typing.Union[str, typing.Sequence[typing.Union[int, float]]]
        # SimpleAlias = Union[int, str]  (2-type, simplest case)
        SimpleAlias = typing.Union[int, str]

        ctx.alias_registry.append(AliasEntry(Color,       "types.Color"))
        ctx.alias_registry.append(AliasEntry(DashArray,   "types.DashArray"))
        ctx.alias_registry.append(AliasEntry(SimpleAlias, "types.Simple"))
        ctx.type_module_imports["types"] = "from demo import types"
        return ctx, Color, DashArray, SimpleAlias

    # ── Alias alone (no None) — must still work ──────────────────────
    def test_alias_alone_preserved(self, ctx_with_aliases):
        ctx, Color, DashArray, SimpleAlias = ctx_with_aliases
        assert annotation_to_str(Color, ctx) == "types.Color"

    def test_simple_alias_alone_preserved(self, ctx_with_aliases):
        ctx, _, _, SimpleAlias = ctx_with_aliases
        assert annotation_to_str(SimpleAlias, ctx) == "types.Simple"

    # ── Alias | None — modern style emits 'types.Alias | None' ──────────
    def test_multi_type_alias_or_none_not_expanded(self, ctx_with_aliases):
        """Color | None must emit 'types.Color | None', not the raw expansion."""
        ctx, Color, _, _ = ctx_with_aliases
        result = annotation_to_str(Color | None, ctx)
        assert result == "types.Color | None", (
            f"Expected 'types.Color | None', got {result!r}\n"
            "Bug: alias was not preserved when used as Alias | None"
        )

    def test_multi_type_alias_or_none_legacy(self, ctx_with_aliases):
        """Legacy style: Color | None → Optional[types.Color]."""
        from stubpy.context import StubConfig
        ctx_modern, Color, _, _ = ctx_with_aliases
        # Build a legacy context with the same alias registry
        legacy = StubContext(config=StubConfig(typing_style="legacy"))
        legacy.alias_registry = list(ctx_modern.alias_registry)
        legacy.type_module_imports.update(ctx_modern.type_module_imports)
        result = annotation_to_str(Color | None, legacy)
        assert result == "Optional[types.Color]"

    def test_dasharray_or_none_not_expanded(self, ctx_with_aliases):
        """DashArray | None must emit 'types.DashArray | None'."""
        ctx, _, DashArray, _ = ctx_with_aliases
        result = annotation_to_str(DashArray | None, ctx)
        assert result == "types.DashArray | None", (
            f"Expected 'types.DashArray | None', got {result!r}"
        )

    def test_two_type_alias_or_none(self, ctx_with_aliases):
        """Simplest case: Union[int, str] | None → types.Simple | None."""
        ctx, _, _, SimpleAlias = ctx_with_aliases
        result = annotation_to_str(SimpleAlias | None, ctx)
        assert result == "types.Simple | None"

    # ── Non-alias multi-union | None — must still expand normally ─────
    def test_non_alias_multi_union_still_expands(self, ctx_with_aliases):
        """A multi-type union with no alias must still expand."""
        import typing
        ctx, _, _, _ = ctx_with_aliases
        unregistered = typing.Union[int, float, None]
        result = annotation_to_str(unregistered, ctx)
        assert "int" in result and "float" in result
        assert "types." not in result

    def test_single_type_or_none_still_modern(self, ctx_with_aliases):
        """Plain str | None emits 'str | None' (modern default)."""
        import typing
        ctx, _, _, _ = ctx_with_aliases
        result = annotation_to_str(typing.Union[str, None], ctx)
        assert result == "str | None"

    def test_single_type_or_none_legacy(self, ctx_with_aliases):
        """Plain str | None emits 'Optional[str]' in legacy mode."""
        import typing
        from stubpy.context import StubConfig
        ctx, _, _, _ = ctx_with_aliases
        legacy = StubContext(config=StubConfig(typing_style="legacy"))
        result = annotation_to_str(typing.Union[str, None], legacy)
        assert result == "Optional[str]"

    # ── Integration: alias | None propagated through kwargs chain ─────
    def test_alias_or_none_propagated_through_kwargs(self):
        """
        End-to-end: when an alias | None annotation is backtraced through
        **kwargs, the generated stub must preserve the alias name.
        Uses the real demo package to match the exact reported bug.
        """
        import tempfile
        from pathlib import Path as _Path
        from stubpy import generate_stub

        src = (
            "from __future__ import annotations\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\n"
            "class Shape(Element):\n"
            "    def __init__(self, stroke: types.Color | None = None, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
            "\n"
            "class Derived(Shape):\n"
            "    def __init__(self, label: str, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        demo_dir = _Path(__file__).resolve().parents[1] / "demo"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
            encoding="utf-8", dir=str(demo_dir)
        ) as f:
            f.write(src)
            tmp = _Path(f.name)
        out = tmp.with_suffix(".pyi")
        try:
            content = generate_stub(str(tmp), str(out))
        finally:
            tmp.unlink(missing_ok=True)
            out.unlink(missing_ok=True)

        derived_sec = content.split("class Derived")[1]
        # Accept both modern and legacy alias forms — the alias MUST be preserved
        alias_preserved = (
            "types.Color | None" in derived_sec
            or "Optional[types.Color]" in derived_sec
        )
        assert alias_preserved, (
            f"Alias not preserved in Derived stub:\n{derived_sec}"
        )
        assert "Union[str, Tuple" not in derived_sec, (
            "Alias was expanded instead of preserved"
        )

    def test_graphics_demo_stroke_preserved(self, demo_dir, tmp_path):
        """
        Regression: graphics.py Shape.stroke (types.Color | None) must emit
        the alias form, not the raw Union[str, Tuple[...], ...] expansion.

        The emitter may produce either the legacy ``Optional[types.Color]`` form
        or the PEP 604 ``types.Color | None`` form — both are correct and both
        preserve the alias.  What must NOT appear is the full raw expansion.
        """
        from stubpy import generate_stub
        out = tmp_path / "graphics.pyi"
        content = generate_stub(str(demo_dir / "graphics.py"), str(out))

        shape_sec = content.split("class Shape")[1].split("\nclass ")[0]
        # Accept either Optional[types.Color] (legacy) or types.Color | None (PEP 604)
        stroke_preserved = (
            "Optional[types.Color]" in shape_sec
            or "types.Color | None" in shape_sec
        )
        assert stroke_preserved, (
            "stroke param should be types.Color | None or Optional[types.Color], "
            f"not raw expansion. Got:\n{shape_sec}"
        )
        dasharray_preserved = (
            "Optional[types.DashArray]" in shape_sec
            or "types.DashArray | None" in shape_sec
        )
        assert dasharray_preserved, (
            "stroke_dasharray should preserve the alias. Got:\n{shape_sec}"
        )
        # The raw expansion must never appear
        assert "Union[str, Tuple[float" not in shape_sec

    def test_graphics_demo_aliases_in_all_subclasses(self, demo_dir, tmp_path):
        """
        The alias preservation must hold for every subclass that backtracks
        stroke through **kwargs: Path, Arc, Rectangle, Square, Circle.
        """
        from stubpy import generate_stub
        out = tmp_path / "graphics2.pyi"
        content = generate_stub(str(demo_dir / "graphics.py"), str(out))

        for cls_name in ("Path", "Arc", "Rectangle", "Square", "Circle"):
            cls_sec = content.split(f"class {cls_name}")[1].split("\nclass ")[0]
            alias_preserved = (
                "types.Color | None" in cls_sec
                or "Optional[types.Color]" in cls_sec
            )
            assert alias_preserved, (
                f"{cls_name}: stroke alias not preserved. Got:\n{cls_sec}"
            )
            assert "Union[str, Tuple[float" not in cls_sec, (
                f"{cls_name}: alias was expanded"
            )


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

    # ── Optional[Alias] — modern style uses X | None ─────────────────
    def test_optional_alias_explicit(self, ctx):
        """typing.Optional[Color] → types.Color | None (modern)"""
        c, Color, _ = ctx
        result = annotation_to_str(typing.Optional[Color], c)
        assert result == "types.Color | None"

    def test_optional_alias_explicit_legacy(self, ctx):
        """typing.Optional[Color] → Optional[types.Color] (legacy)"""
        from stubpy.context import StubConfig
        c_orig, Color, _ = ctx
        legacy = StubContext(config=StubConfig(typing_style="legacy"))
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
        from stubpy.context import StubConfig
        c_orig, Color, _ = ctx
        legacy = StubContext(config=StubConfig(typing_style="legacy"))
        legacy.alias_registry = c_orig.alias_registry[:]
        legacy.type_module_imports.update(c_orig.type_module_imports)
        assert annotation_to_str(typing.Union[Color, None], legacy) == "Optional[types.Color]"

    def test_optional_dasharray(self, ctx):
        """typing.Optional[DashArray] → types.DashArray | None (modern)"""
        c, _, DashArray = ctx
        result = annotation_to_str(typing.Optional[DashArray], c)
        assert result == "types.DashArray | None"

    # ── Alias as a generic argument (List, Dict, Tuple, Set) ─────────
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

    # ── Unfixable: Python flattens Union[Alias, OtherType] ───────────
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
        assert "types.Color" in result  # this will never pass — xfail

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
        assert "types.Color" in result and "types.DashArray" in result  # xfail

    # ── Integration: Optional[Alias] written in source code ──────────
    def test_optional_alias_in_generated_stub(self, demo_dir, tmp_path):
        """
        When a developer writes ``Optional[types.Color]`` explicitly in source
        (rather than ``types.Color | None``), the stub must still emit
        ``Optional[types.Color]``.
        """
        from stubpy import generate_stub
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
        out = tmp_path / "widget.pyi"
        content = generate_stub(str(tmp), str(out))
        widget_sec = content.split("class Widget")[1]
        assert "Optional[types.Color]" in widget_sec, (
            f"Expected Optional[types.Color] in stub:\n{widget_sec}"
        )
        assert "Union[str, Tuple" not in widget_sec


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
        import typing as _t
        from demo import types as demo_types
        ctx.alias_registry.append(AliasEntry(demo_types.Length, "types.Length"))
        ctx.type_module_imports["types"] = "from demo import types"
        result = annotation_to_str(_t.Tuple[demo_types.Length, ...], ctx)
        assert result == "Tuple[types.Length, ...]"
        assert "Ellipsis" not in result

    def test_builtin_tuple_variadic_with_alias(self, empty_ctx):
        """``tuple[types.Length, ...]`` (PEP 585) also works."""
        ctx = empty_ctx
        from demo import types as demo_types
        ctx.alias_registry.append(AliasEntry(demo_types.Length, "types.Length"))
        ctx.type_module_imports["types"] = "from demo import types"
        result = annotation_to_str(tuple[demo_types.Length, ...], ctx)
        assert result == "tuple[types.Length, ...]"
        assert "Ellipsis" not in result


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

    # ── list / List ───────────────────────────────────────────────────
    def test_list_alias(self, ctx):
        assert annotation_to_str(list[demo_types_color(ctx)], ctx) == "list[types.Color]"

    def test_List_alias(self, ctx):
        from demo import types as dt
        assert annotation_to_str(typing.List[dt.Color], ctx) == "List[types.Color]"

    # ── tuple with two alias args ─────────────────────────────────────
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

    # ── tuple with alias + plain type mix ─────────────────────────────
    def test_tuple_alias_and_plain_lowercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[dt.Color, int, float], ctx)
        assert result == "tuple[types.Color, int, float]"

    def test_Tuple_alias_and_plain_uppercase(self, ctx):
        from demo import types as dt
        result = annotation_to_str(typing.Tuple[dt.Color, int, float], ctx)
        assert result == "Tuple[types.Color, int, float]"

    # ── tuple[T, ...] variadic (also tests Ellipsis fix) ─────────────
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

    # ── nested containers ─────────────────────────────────────────────
    def test_list_of_tuple_with_aliases(self, ctx):
        from demo import types as dt
        result = annotation_to_str(list[tuple[dt.Color, dt.Length]], ctx)
        assert result == "list[tuple[types.Color, types.Length]]"

    def test_tuple_of_list_with_alias(self, ctx):
        from demo import types as dt
        result = annotation_to_str(tuple[list[dt.Color], dt.Length], ctx)
        assert result == "tuple[list[types.Color], types.Length]"


def demo_types_color(ctx):
    """Helper: return Color from the first alias registry entry named types.Color."""
    from demo import types as dt
    return dt.Color


class TestUnionAliasViaASTPrePass:
    """
    Tests for the previously-unfixable Union[Alias, OtherType] case, now
    resolved via the AST pre-pass.

    At runtime, ``Union[types.Color, int]`` where ``Color = Union[str, Tuple[...]]``
    is immediately flattened to ``Union[str, Tuple[...], int]`` by Python.
    The alias boundary is permanently lost from the type object.

    The fix: the AST pre-pass stores the raw annotation string *before*
    evaluation (e.g. ``"Union[types.Color, int]"``).  The emitter's
    ``_get_raw_ast_annotations`` looks this up from the symbol table and
    passes it to ``format_param`` as ``raw_ann_override``.  When the raw
    string references a registered alias module prefix, it is used directly,
    bypassing the flattened runtime annotation entirely.
    """

    def _gen(self, src: str, tmp_path) -> str:
        """Write *src* to a temp file in demo/ and return the generated stub."""
        import tempfile
        from pathlib import Path as _P
        from stubpy import generate_stub
        demo = _P(__file__).resolve().parents[1] / "demo"
        p = _P(tempfile.mktemp(suffix=".py", dir=str(demo)))
        p.write_text(src, encoding="utf-8")
        out = _P(tempfile.mktemp(suffix=".pyi"))
        try:
            return generate_stub(str(p), str(out))
        finally:
            p.unlink(missing_ok=True)
            out.unlink(missing_ok=True)

    def test_union_alias_and_int(self, tmp_path):
        """``Union[types.Color, int]`` must emit as-is, not expanded."""
        src = (
            "from __future__ import annotations\n"
            "from typing import Union\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass W(Element):\n"
            "    def __init__(self, x: Union[types.Color, int], **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        content = self._gen(src, tmp_path)
        w_sec = content.split("class W")[1]
        assert "Union[types.Color, int]" in w_sec, (
            f"Expected 'Union[types.Color, int]', got:\n{w_sec}"
        )
        assert "Union[str, Tuple" not in w_sec

    def test_union_two_aliases(self, tmp_path):
        """``Union[types.Color, types.Length]`` must preserve both aliases."""
        src = (
            "from __future__ import annotations\n"
            "from typing import Union\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass W(Element):\n"
            "    def __init__(self, x: Union[types.Color, types.Length], **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        content = self._gen(src, tmp_path)
        w_sec = content.split("class W")[1]
        assert "Union[types.Color, types.Length]" in w_sec, (
            f"Expected Union[types.Color, types.Length], got:\n{w_sec}"
        )
        assert "Union[str, Tuple" not in w_sec

    def test_union_two_aliases_with_none(self, tmp_path):
        """``Union[types.Color, types.Length, None]`` must preserve both aliases."""
        src = (
            "from __future__ import annotations\n"
            "from typing import Union\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass W(Element):\n"
            "    def __init__(self, x: Union[types.Color, types.Length, None] = None,\n"
            "                 **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        content = self._gen(src, tmp_path)
        w_sec = content.split("class W")[1]
        assert "Union[types.Color, types.Length, None]" in w_sec, (
            f"Got:\n{w_sec}"
        )

    def test_union_alias_and_int_pep604_syntax(self, tmp_path):
        """``types.Color | int`` written with PEP 604 syntax also preserved."""
        src = (
            "from __future__ import annotations\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass W(Element):\n"
            "    def __init__(self, x: types.Color | int, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        content = self._gen(src, tmp_path)
        w_sec = content.split("class W")[1]
        assert "types.Color" in w_sec, f"Alias lost:\n{w_sec}"
        assert "Union[str, Tuple" not in w_sec

    def test_raw_override_does_not_affect_non_alias_params(self, tmp_path):
        """Plain params without aliases must still use the runtime path."""
        src = (
            "from __future__ import annotations\n"
            "from demo import types\n"
            "from demo.element import Element\n"
            "\nclass W(Element):\n"
            "    def __init__(self, x: int, y: str = 'hi', **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        content = self._gen(src, tmp_path)
        w_sec = content.split("class W")[1]
        assert "x: int" in w_sec
        assert "y: str = 'hi'" in w_sec

    def test_format_param_raw_override_used_when_alias_present(self, empty_ctx):
        """Unit test: format_param uses raw_ann_override when alias prefix found."""
        import inspect
        from stubpy.annotations import format_param
        from demo import types as dt

        ctx = empty_ctx
        ctx.alias_registry.append(AliasEntry(dt.Color, "types.Color"))
        ctx.type_module_imports["types"] = "from demo import types"

        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        result = format_param(p, {}, ctx, raw_ann_override="Union[types.Color, int]")
        assert result == "x: Union[types.Color, int]"

    def test_format_param_raw_override_ignored_without_alias(self, empty_ctx):
        """format_param ignores raw_ann_override when it has no alias prefix."""
        import inspect, typing
        from stubpy.annotations import format_param

        ctx = empty_ctx  # no aliases registered
        p = inspect.Parameter(
            "x",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=int,
        )
        result = format_param(p, {"x": int}, ctx, raw_ann_override="Union[int, str]")
        # No alias prefix in raw_ann → falls back to runtime annotation
        assert result == "x: int"

    def test_raw_preserves_aliases_helper(self, empty_ctx):
        """_raw_preserves_aliases returns True iff alias prefix is in the string."""
        from stubpy.annotations import _raw_preserves_aliases

        ctx = empty_ctx
        ctx.type_module_imports["types"] = "from demo import types"

        assert _raw_preserves_aliases("Union[types.Color, int]", ctx) is True
        assert _raw_preserves_aliases("types.Length", ctx) is True
        assert _raw_preserves_aliases("Union[int, str]", ctx) is False
        assert _raw_preserves_aliases("int", ctx) is False
        assert _raw_preserves_aliases("", ctx) is False


# ---------------------------------------------------------------------------
# TypeVar annotation rendering
# ---------------------------------------------------------------------------

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

    def test_typevartuple_renders_as_name(self, empty_ctx):
        import typing
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

        b = Box.__orig_bases__[0]  # Generic[T]
        result = annotation_to_str(b, empty_ctx)
        assert "T" in result
        assert "~" not in result
