"""Tests for stubpy.analysis.loader."""
from __future__ import annotations

import tempfile
from pathlib import Path

from stubpy.analysis.loader import load_module
from stubpy.core.diagnostics import DiagnosticCollector, DiagnosticStage


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
