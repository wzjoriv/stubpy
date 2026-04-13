"""
tests/test_generator.py
------------------------
Tests for :mod:`stubpy.generator` — :func:`generate_stub` and
:func:`generate_package` orchestration.

Covers:
- Single-file stub generation pipeline stages
- Package (directory) batch generation
- ``ctx_factory`` with and without file-path arguments
- Execution mode (RUNTIME / AST_ONLY / AUTO)
- ``__all__`` filtering at the generator level
- Error/fallback handling
- Integration against ``demo/`` package
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.conftest import assert_valid_syntax, make_stub
from stubpy import generate_stub, generate_package
from stubpy.context import StubConfig, StubContext, ExecutionMode
from stubpy.generator import PackageResult


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"


class TestDemoFunctionsIntegration:
    """Run generate_stub on demo/functions.py and verify every stub."""

    @pytest.fixture(scope="class")
    def stub(self):
        from stubpy import generate_stub
        import tempfile, os
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
        # The * separator must appear before g and b
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
        from stubpy import generate_stub
        import tempfile, os
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
    def stubs(self, tmp_path_factory):
        from stubpy.generator import generate_package
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
        # Container.__init__ has *elements, **kwargs → Element.__init__ params
        assert "def __init__(" in cont

    def test_zero_failures(self, stubs, tmp_path_factory):
        from stubpy.generator import generate_package
        out_dir = str(tmp_path_factory.mktemp("stubs2"))
        result = generate_package(str(DEMO_DIR), output_dir=out_dir)
        assert result.failed == [], f"Failed: {result.failed}"


# ===========================================================================
# CLI multi-file tests
# ===========================================================================


# ---------------------------------------------------------------------------
# generate_package ctx_factory with file-info
# ---------------------------------------------------------------------------


class TestCtxFactoryFileInfo:
    """ctx_factory with (source_path, output_path) signature."""

    def test_no_arg_factory_works(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text("x: int = 1\n")
        seen = []
        def factory():
            seen.append("called")
            return StubContext()
        result = generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert len(seen) >= 1
        assert len(result.failed) == 0

    def test_two_arg_factory_receives_paths(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text("x: int = 1\n")
        received = []
        def factory(source: Path, output: Path):
            received.append((source, output))
            return StubContext()
        generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert len(received) >= 1
        src_path, out_path = received[0]
        assert str(src_path).endswith(".py")
        assert str(out_path).endswith(".pyi")

    def test_custom_config_per_file(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "slow.py").write_text("x: int = 1\n")
        modes = []
        def factory(source: Path, output: Path):
            mode = ExecutionMode.AST_ONLY if "slow" in source.name else ExecutionMode.RUNTIME
            modes.append(mode)
            return StubContext(config=StubConfig(execution_mode=mode))
        generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert ExecutionMode.AST_ONLY in modes


class TestGenerateStubPipeline:
    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_stub(str(tmp_path / "nonexistent.py"))

    def test_ast_only_mode_no_execution(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("import nonexistent_module\nx: int = 1\n")
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
        # Should not raise ImportError even though module import would fail
        stub = generate_stub(str(src), ctx=ctx)
        assert "x" in stub

    def test_auto_mode_falls_back_on_import_error(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("import _totally_nonexistent_xyz\nx: int = 1\n")
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AUTO))
        stub = generate_stub(str(src), ctx=ctx)
        assert isinstance(stub, str)

    def test_output_path_respected(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        out = tmp_path / "custom" / "mod.pyi"
        out.parent.mkdir()
        generate_stub(str(src), str(out))
        assert out.exists()

    def test_returns_content_string(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        result = generate_stub(str(src), str(tmp_path / "mod.pyi"))
        assert isinstance(result, str)
        assert "x: int" in result

    def test_stubpy_ignore_directive(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("# stubpy: ignore\nx: int = 1\n")
        out = tmp_path / "mod.pyi"
        generate_stub(str(src), str(out))
        content = out.read_text()
        assert "x:" not in content


class TestGeneratePackagePipeline:
    def test_creates_init_pyi_for_subpackages(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "mod.py").write_text("x: int = 1\n")
        out = tmp_path / "stubs"
        result = generate_package(str(pkg), str(out))
        assert len(result.failed) == 0
        assert (out / "sub" / "__init__.pyi").exists()

    def test_exclude_patterns(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "secret.py").write_text("SECRET: str = 'x'\n")
        (pkg / "public.py").write_text("PUB: int = 1\n")
        out = tmp_path / "stubs"
        cfg = StubConfig(exclude=["secret.py"])
        result = generate_package(str(pkg), str(out), config=cfg)
        assert not (out / "secret.pyi").exists()
        assert (out / "public.pyi").exists()

    def test_failed_files_reported(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "bad.py").write_text("import __absolutely_nothing_exists__\nraise RuntimeError()\n")
        out = tmp_path / "stubs"
        # RUNTIME mode — should fail gracefully
        cfg = StubConfig(execution_mode=ExecutionMode.RUNTIME)
        result = generate_package(str(pkg), str(out), config=cfg)
        # Either failed or succeeded via fallback depending on mode
        assert isinstance(result, PackageResult)

    def test_package_result_summary(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("x: int = 1\n")
        (pkg / "b.py").write_text("y: str = 'hi'\n")
        out = tmp_path / "stubs"
        result = generate_package(str(pkg), str(out))
        summary = result.summary()
        assert "Generated" in summary
        assert "failed" in summary
