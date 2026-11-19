"""Tests for python -m stubpy."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ``python -m stubpy`` with no inherited stdin (GraalPy on Windows cannot pass the console handle on)."""
    return subprocess.run(
        [sys.executable, "-m", "stubpy", *args],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=str(ROOT),
    )


@pytest.mark.skipif(sys.platform == "emscripten", reason="no subprocess on Emscripten")
class TestCLIFlags:
    """Tests for CLI flags: --verbose, --strict, --include-private."""

    def test_verbose_flag_accepted(self, tmp_path):
        """--verbose must not cause argparse to error."""
        src = tmp_path / "simple.py"
        src.write_text("class Foo:\n    x: int = 1\n")
        result = _run(str(src), "--verbose")
        assert result.returncode == 0, result.stderr
        assert "wrote" in result.stdout
        assert "Symbol table built" in result.stderr

    def test_strict_flag_accepted(self, tmp_path):
        """--strict must not cause argparse to error on a clean file."""
        src = tmp_path / "clean.py"
        src.write_text("class Bar:\n    pass\n")
        result = _run(str(src), "--strict")
        assert result.returncode == 0, result.stderr

    def test_render_prints_the_stub(self, tmp_path):
        """``stubpy render`` prints the stub and writes nothing."""
        src = tmp_path / "mod.py"
        src.write_text("class Widget:\n    def __init__(self, x: int) -> None: pass\n")
        result = _run("render", str(src))
        assert result.returncode == 0
        assert "class Widget:" in result.stdout
        assert not src.with_suffix(".pyi").exists()

    def test_file_not_found_returns_2(self):
        """A target that does not exist is a usage error: exit code 2."""
        result = _run("/nonexistent/file.py")
        assert result.returncode == 2
        assert "error" in result.stderr
