"""Tests for stubpy.core.pipeline.render_module and its use through the public API."""
from __future__ import annotations

import pytest

import stubpy
from stubpy.config import Config, Mode
from stubpy.core.context import StubContext
from stubpy.core.pipeline import render_module


class TestGenerateStubPipeline:
    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            stubpy.render(str(tmp_path / "nonexistent.py"))

    def test_render_module_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_module(tmp_path / "nonexistent.py", StubContext())

    def test_ast_only_mode_no_execution(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("import nonexistent_module\nx: int = 1\n")
        ctx = StubContext(config=Config(mode=Mode.AST))
        stub = render_module(str(src), ctx)
        assert "x" in stub

    def test_auto_mode_falls_back_on_import_error(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("import _totally_nonexistent_xyz\nx: int = 1\n")
        ctx = StubContext(config=Config(mode=Mode.AUTO))
        stub = render_module(str(src), ctx)
        assert isinstance(stub, str)

    def test_output_path_respected(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        out = tmp_path / "custom" / "mod.pyi"
        report = stubpy.generate(str(src), out)
        assert out.exists()
        assert report.written == [out]

    def test_returns_content_string(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        result = stubpy.render(str(src)).text
        assert isinstance(result, str)
        assert "x: int" in result

    def test_stubpy_ignore_directive(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("# stubpy: ignore\nx: int = 1\n")
        out = tmp_path / "mod.pyi"
        stubpy.generate(str(src))
        content = out.read_text()
        assert "x:" not in content
