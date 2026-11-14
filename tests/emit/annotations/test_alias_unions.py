"""Alias preservation in Optional and Union annotations."""
from __future__ import annotations

import inspect
import typing

import pytest

import stubpy
from stubpy.config import Config
from stubpy.core.context import AliasEntry, StubContext
from stubpy.emit.annotations import (
    annotation_to_str,
    format_param,
)


@pytest.fixture
def ctx() -> StubContext:
    return StubContext()


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
        ctx = StubContext()
        Color = typing.Union[
            str,
            typing.Tuple[float, float, float],
            typing.Tuple[float, float, float, float],
        ]
        DashArray = typing.Union[str, typing.Sequence[typing.Union[int, float]]]
        SimpleAlias = typing.Union[int, str]

        ctx.alias_registry.append(AliasEntry(Color,       "types.Color"))
        ctx.alias_registry.append(AliasEntry(DashArray,   "types.DashArray"))
        ctx.alias_registry.append(AliasEntry(SimpleAlias, "types.Simple"))
        ctx.type_module_imports["types"] = "from demo import types"
        return ctx, Color, DashArray, SimpleAlias

    def test_alias_alone_preserved(self, ctx_with_aliases):
        ctx, Color, DashArray, SimpleAlias = ctx_with_aliases
        assert annotation_to_str(Color, ctx) == "types.Color"

    def test_simple_alias_alone_preserved(self, ctx_with_aliases):
        ctx, _, _, SimpleAlias = ctx_with_aliases
        assert annotation_to_str(SimpleAlias, ctx) == "types.Simple"

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
        ctx_modern, Color, _, _ = ctx_with_aliases
        legacy = StubContext(config=Config(union_style="legacy"))
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

    def test_non_alias_multi_union_still_expands(self, ctx_with_aliases):
        """A multi-type union with no alias must still expand."""
        ctx, _, _, _ = ctx_with_aliases
        unregistered = typing.Union[int, float, None]
        result = annotation_to_str(unregistered, ctx)
        assert "int" in result and "float" in result
        assert "types." not in result

    def test_single_type_or_none_still_modern(self, ctx_with_aliases):
        """Plain str | None emits 'str | None' (modern default)."""
        ctx, _, _, _ = ctx_with_aliases
        result = annotation_to_str(typing.Union[str, None], ctx)
        assert result == "str | None"

    def test_single_type_or_none_legacy(self, ctx_with_aliases):
        """Plain str | None emits 'Optional[str]' in legacy mode."""

        from stubpy.config import Config
        ctx, _, _, _ = ctx_with_aliases
        legacy = StubContext(config=Config(union_style="legacy"))
        result = annotation_to_str(typing.Union[str, None], legacy)
        assert result == "Optional[str]"

    def test_alias_or_none_propagated_through_kwargs(self):
        """
        End-to-end: when an alias | None annotation is backtraced through
        **kwargs, the generated stub must preserve the alias name.
        Uses the real demo package to match the exact reported bug.
        """
        import tempfile
        from pathlib import Path as _Path


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
        demo_dir = _Path(__file__).resolve().parents[3] / "demo"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
            encoding="utf-8", dir=str(demo_dir)
        ) as f:
            f.write(src)
            tmp = _Path(f.name)
        out = tmp.with_suffix(".pyi")
        try:
            content = stubpy.render(str(tmp)).text
        finally:
            tmp.unlink(missing_ok=True)
            out.unlink(missing_ok=True)

        derived_sec = content.split("class Derived")[1]
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
        content = stubpy.render(str(demo_dir / "graphics.py")).text

        shape_sec = content.split("class Shape")[1].split("\nclass ")[0]
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
        assert "Union[str, Tuple[float" not in shape_sec

    def test_graphics_demo_aliases_in_all_subclasses(self, demo_dir, tmp_path):
        """
        The alias preservation must hold for every subclass that backtracks
        stroke through **kwargs: Path, Arc, Rectangle, Square, Circle.
        """
        content = stubpy.render(str(demo_dir / "graphics.py")).text

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

        demo = _P(__file__).resolve().parents[3] / "demo"
        p = _P(tempfile.mktemp(suffix=".py", dir=str(demo)))
        p.write_text(src, encoding="utf-8")
        out = _P(tempfile.mktemp(suffix=".pyi"))
        try:
            return stubpy.render(str(p)).text
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

        from demo import types as dt

        ctx = empty_ctx
        ctx.alias_registry.append(AliasEntry(dt.Color, "types.Color"))
        ctx.type_module_imports["types"] = "from demo import types"

        p = inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)
        result = format_param(p, {}, ctx, raw_ann_override="Union[types.Color, int]")
        assert result == "x: Union[types.Color, int]"

    def test_format_param_raw_override_ignored_without_alias(self, empty_ctx):
        """format_param ignores raw_ann_override when it has no alias prefix."""

        ctx = empty_ctx
        p = inspect.Parameter(
            "x",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=int,
        )
        result = format_param(p, {"x": int}, ctx, raw_ann_override="Union[int, str]")
        assert result == "x: int"

    def test_raw_preserves_aliases_helper(self, empty_ctx):
        """_raw_preserves_aliases returns True iff alias prefix is in the string."""
        from stubpy.emit.annotations.params import _raw_preserves_aliases

        ctx = empty_ctx
        ctx.type_module_imports["types"] = "from demo import types"

        assert _raw_preserves_aliases("Union[types.Color, int]", ctx) is True
        assert _raw_preserves_aliases("types.Length", ctx) is True
        assert _raw_preserves_aliases("Union[int, str]", ctx) is False
        assert _raw_preserves_aliases("int", ctx) is False
        assert _raw_preserves_aliases("", ctx) is False
