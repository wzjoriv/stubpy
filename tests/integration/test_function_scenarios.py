"""End-to-end stubs for module-level functions: forwarding, separators, privacy."""
from __future__ import annotations

from stubpy.config import Config
from stubpy.core.pipeline import render_module
from stubpy.state.context import StubContext
from tests.conftest import assert_valid_syntax


def _signature(stub: str, name: str) -> str:
    """Return the parameter text of ``def name(...)`` in *stub*."""
    return stub.split(f"def {name}(")[1].split(") -> ")[0]


class TestFunctionScenarios:
    def test_syntax_valid(self, functions_stub):
        assert_valid_syntax(functions_stub)

    def test_make_color_unchanged(self, functions_stub):
        sig = _signature(functions_stub, "make_color")
        for p in ("r: float", "g: float", "b: float", "a: float = 1.0"):
            assert p in sig

    def test_make_color_red_kwargs_expanded(self, functions_stub):
        sig = _signature(functions_stub, "make_color_red")
        assert "**kwargs" not in sig
        assert "g: float" in sig
        assert "b: float" in sig
        assert "a: float = 1.0" in sig

    def test_make_color_red_default_ordering_valid(self, functions_stub):
        """r=1.0 has a default, so absorbed g and b must be keyword-only."""
        sig = _signature(functions_stub, "make_color_red")
        star_idx = sig.find("*,")
        assert star_idx != -1, "bare * separator missing"
        assert sig.find("g: float") > star_idx
        assert sig.find("b: float") > star_idx

    def test_make_color_blue_kwargs_expanded(self, functions_stub):
        sig = _signature(functions_stub, "make_color_blue")
        assert "r: float" in sig
        assert "g: float" in sig
        assert sig.count("b: float") == 1
        assert "**kwargs" not in sig

    def test_make_color_tinted_chained(self, functions_stub):
        """make_color_tinted -> make_color_red -> make_color: depth-2 chain."""
        sig = _signature(functions_stub, "make_color_tinted")
        assert "tint: float" in sig
        assert "g: float" in sig
        assert "b: float" in sig
        assert "r:" not in sig
        assert "**kwargs" not in sig

    def test_normalise_range_pos_only(self, functions_stub):
        assert "/" in _signature(functions_stub, "normalise_range")

    def test_scaled_clamp_pos_only_and_kw_only(self, functions_stub):
        sig = _signature(functions_stub, "scaled_clamp")
        assert "/" in sig
        assert "*" in sig
        assert sig.index("/") < sig.index("*") < sig.index("scale")

    def test_stack_colors_typed_args(self, functions_stub):
        assert "*colors: types.Color" in _signature(functions_stub, "stack_colors")

    def test_blend_colors_args_and_kwargs(self, functions_stub):
        """Typed *args kept and **kwargs expanded from both callees."""
        sig = _signature(functions_stub, "blend_colors")
        assert "*colors: types.Color" in sig
        assert "gamma: float" in sig
        assert "**kwargs" not in sig

    def test_async_function(self, functions_stub):
        assert "async def render_to_file(" in functions_stub

    def test_alias_module_imported(self, functions_stub):
        assert "from drawkit import types" in functions_stub

    def test_no_private_functions_by_default(self, functions_stub):
        assert "_resolve_color_string" not in functions_stub
        assert "_bbox_union" not in functions_stub

    def test_private_functions_with_flag(self, drawkit):
        ctx = StubContext(config=Config(include_private=True))
        content = render_module(str(drawkit / "functions.py"), ctx)
        assert "def _resolve_color_string(color: str) -> types.Color:" in content
        assert "def _bbox_union(*boxes: types.BoundingBox) -> types.BoundingBox:" in content
