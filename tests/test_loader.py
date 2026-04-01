"""
tests/test_loader.py
----------------------------
CLI and diagnostics tests for stubpy.loader:
  - diagnostics parameter
  - error recording in DiagnosticCollector
"""
from __future__ import annotations
import sys, tempfile
from pathlib import Path

from stubpy.diagnostics import DiagnosticCollector, DiagnosticStage
from stubpy.loader import load_module


class TestLoaderDiagnostics:
    def test_file_not_found_recorded_in_diagnostics(self):
        d = DiagnosticCollector()
        try:
            load_module("/nonexistent/file.py", diagnostics=d)
        except FileNotFoundError:
            pass
        assert d.has_errors()
        assert d.errors[0].stage == DiagnosticStage.LOAD

    def test_file_not_found_still_raises(self):
        d = DiagnosticCollector()
        raised = False
        try:
            load_module("/nonexistent/file.py", diagnostics=d)
        except FileNotFoundError:
            raised = True
        assert raised

    def test_without_diagnostics_raises(self):
        raised = False
        try:
            load_module("/nonexistent/file.py")
        except FileNotFoundError:
            raised = True
        assert raised

    def test_success_no_errors(self):
        d = DiagnosticCollector()
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write("x = 1\n")
            p = Path(f.name)
        mod, path, name = load_module(str(p), diagnostics=d)
        assert not d.has_errors()
        assert mod.x == 1

    def test_error_message_contains_path(self):
        d = DiagnosticCollector()
        try:
            load_module("/no/such/file.py", diagnostics=d)
        except FileNotFoundError:
            pass
        assert "no/such/file.py" in d.errors[0].message or "file.py" in d.errors[0].message

    def test_diagnostics_none_behaves_as_before(self):
        """None diagnostics should behave identically to v0.1."""
        raised = False
        try:
            load_module("/bad/path/file.py", diagnostics=None)
        except FileNotFoundError:
            raised = True
        assert raised


class TestCLIFlags:
    """Tests for CLI flags: --verbose, --strict, --include-private."""

    def test_verbose_flag_accepted(self, tmp_path):
        """--verbose must not cause argparse to error."""
        import subprocess, sys
        src = tmp_path / "simple.py"
        src.write_text("class Foo:\n    x: int = 1\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--verbose"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0, result.stderr
        assert "Stub written to" in result.stdout
    def test_strict_flag_accepted(self, tmp_path):
        """--strict must not cause argparse to error on a clean file."""
        import subprocess, sys
        src = tmp_path / "clean.py"
        src.write_text("class Bar:\n    pass\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--strict"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0, result.stderr

    def test_print_flag_still_works(self, tmp_path):
        """The --print flag must still work."""
        import subprocess, sys
        src = tmp_path / "mod.py"
        src.write_text("class Widget:\n    def __init__(self, x: int) -> None: pass\n")
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", str(src), "--print"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 0
        assert "class Widget:" in result.stdout

    def test_file_not_found_returns_1(self):
        """Non-existent file must return exit code 1."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "stubpy", "/nonexistent/file.py"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        assert result.returncode == 1
        assert "Error" in result.stderr
