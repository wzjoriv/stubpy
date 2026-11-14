"""Tests for python -m stubpy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "emscripten", reason="no subprocess on Emscripten")
class TestCLIFlags:
    """Tests for CLI flags: --verbose, --strict, --include-private."""

    def test_verbose_flag_accepted(self, tmp_path):
        """--verbose must not cause argparse to error."""
        import subprocess
        src = tmp_path / "simple.py"
        src.write_text("class Foo:\n    x: int = 1\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--verbose"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert result.returncode == 0, result.stderr
        assert "Stub written to" in result.stdout
    def test_strict_flag_accepted(self, tmp_path):
        """--strict must not cause argparse to error on a clean file."""
        import subprocess
        src = tmp_path / "clean.py"
        src.write_text("class Bar:\n    pass\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--strict"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert result.returncode == 0, result.stderr

    def test_print_flag_still_works(self, tmp_path):
        """The --print flag must still work."""
        import subprocess
        src = tmp_path / "mod.py"
        src.write_text("class Widget:\n    def __init__(self, x: int) -> None: pass\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--print"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert result.returncode == 0
        assert "class Widget:" in result.stdout

    def test_file_not_found_returns_1(self):
        """Non-existent file must return exit code 1."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", "/nonexistent/file.py"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        assert result.returncode == 1
        assert "Error" in result.stderr
