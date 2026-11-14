"""End-to-end stubs for demo/functions.py and the demo package."""
from __future__ import annotations

from pathlib import Path

import pytest

from stubpy import generate_stub
from stubpy.config import StubConfig
from stubpy.core.context import StubContext
from tests.conftest import assert_valid_syntax

ROOT = Path(__file__).resolve().parents[2]


DEMO_DIR = ROOT / "demo"


class TestDemoFunctionsIntegration:
    """Run generate_stub on demo/functions.py and verify every stub."""

    @pytest.fixture(scope="class")
    @classmethod
    def stub(cls):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "functions.pyi")
            content = generate_stub(str(DEMO_DIR / "functions.py"), out)
        return content

    def test_syntax_valid(self, stub):
        assert_valid_syntax(stub)

    def test_make_color_correct(self, stub):
        """Base function unchanged."""
        assert "def make_color(" in stub
        assert "r: float" in stub
        assert "g: float" in stub
        assert "b: float" in stub
        assert "a: float = 1.0" in stub

    def test_make_color_red_kwargs_expanded(self, stub):
        """make_color_red(**kwargs) → expanded with g, b, a from make_color."""
        assert "def make_color_red(" in stub
        assert "**kwargs" not in stub.split("def make_color_red(")[1].split(")")[0]
        assert "g: float" in stub
        assert "b: float" in stub

    def test_make_color_red_default_ordering_valid(self, stub):
        """r=1.0 has default; absorbed g,b must be keyword-only (*) to stay valid."""
        section = stub.split("def make_color_red(")[1].split(") -> ")[0]
        star_idx = section.find("*,")
        g_idx = section.find("g: float")
        b_idx = section.find("b: float")
        assert star_idx != -1, "bare * separator missing"
        assert g_idx > star_idx
        assert b_idx > star_idx

    def test_make_color_blue_kwargs_expanded(self, stub):
        assert "def make_color_blue(" in stub
        assert "r: float" in stub

    def test_make_color_tinted_chained(self, stub):
        """make_color_tinted → make_color_red → make_color: depth-2 chain."""
        assert "def make_color_tinted(" in stub
        section = stub.split("def make_color_tinted(")[1].split(") -> ")[0]
        assert "tint" in section
        assert "g" in section
        assert "b" in section
        assert "**kwargs" not in section

    def test_normalise_range_pos_only(self, stub):
        """Positional-only params emit the / separator."""
        section = stub.split("def normalise_range(")[1].split(") -> ")[0]
        assert "/" in section

    def test_scaled_clamp_pos_only_and_kw_only(self, stub):
        """scaled_clamp has both / and * separators."""
        section = stub.split("def scaled_clamp(")[1].split(") -> ")[0]
        assert "/" in section
        assert "*" in section
        assert "scale" in section

    def test_stack_colors_typed_args(self, stub):
        """Typed *args preserved in stack_colors."""
        assert "*colors: types.Color" in stub

    def test_blend_colors_args_and_kwargs(self, stub):
        """blend_colors: *args typed + **kwargs expanded; no residual **kwargs."""
        section = stub.split("def blend_colors(")[1].split(") -> ")[0]
        assert "*colors" in section
        assert "**kwargs" not in section
        assert "gamma" in section

    def test_async_render_to_file(self, stub):
        assert "async def render_to_file(" in stub

    def test_no_private_functions_by_default(self, stub):
        assert "_resolve_color_string" not in stub
        assert "_bbox_union" not in stub

    def test_private_functions_with_flag(self):
        import os
        import tempfile

        cfg = StubConfig(include_private=True)
        ctx = StubContext(config=cfg)
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "functions.pyi")
            content = generate_stub(str(DEMO_DIR / "functions.py"), out, ctx=ctx)
        assert "_resolve_color_string" in content
        assert "_bbox_union" in content


class TestDemoPackageIntegration:
    """Run generate_stub on the entire demo package and sanity-check all stubs."""

    @pytest.fixture(scope="class")
    @classmethod
    def stubs(cls, tmp_path_factory):
        from stubpy.core.package import generate_package
        out_dir = str(tmp_path_factory.mktemp("stubs"))
        result = generate_package(str(DEMO_DIR), output_dir=out_dir)
        files = {p.name: p.read_text() for p in result.stubs_written}
        return files

    def test_all_modules_generated(self, stubs):
        expected = {"functions.pyi", "container.pyi", "element.pyi",
                    "graphics.pyi", "mixed.pyi", "types.pyi", "variables.pyi"}
        assert expected.issubset(set(stubs.keys()))

    def test_all_stubs_valid_syntax(self, stubs):
        for name, content in stubs.items():
            assert_valid_syntax(content), f"{name} has invalid syntax"

    def test_functions_kwargs_expanded(self, stubs):
        funcs = stubs.get("functions.pyi", "")
        assert "def make_color_red(" in funcs
        assert "**kwargs" not in funcs.split("def make_color_red(")[1].split(")")[0]

    def test_container_kwargs_resolved(self, stubs):
        cont = stubs.get("container.pyi", "")
        assert "def __init__(" in cont

    def test_zero_failures(self, stubs, tmp_path_factory):
        from stubpy.core.package import generate_package
        out_dir = str(tmp_path_factory.mktemp("stubs2"))
        result = generate_package(str(DEMO_DIR), output_dir=out_dir)
        assert result.failed == [], f"Failed: {result.failed}"
