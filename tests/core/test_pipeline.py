"""Tests for stubpy.core.pipeline.generate_stub."""
from __future__ import annotations

import pytest

from stubpy import generate_stub
from stubpy.config import ExecutionMode, StubConfig
from stubpy.core.context import StubContext


class TestGenerateStubPipeline:
    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_stub(str(tmp_path / "nonexistent.py"))

    def test_ast_only_mode_no_execution(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("import nonexistent_module\nx: int = 1\n")
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
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
