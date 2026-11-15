"""Tests for stubpy.analysis.loader."""
from __future__ import annotations

import tempfile
from pathlib import Path

from stubpy.analysis.loader import load_module
from stubpy.core.diagnostics import DiagnosticCollector, Stage


class TestLoaderDiagnostics:
    def test_file_not_found_recorded_in_diagnostics(self):
        d = DiagnosticCollector()
        try:
            load_module("/nonexistent/file.py", diagnostics=d)
        except FileNotFoundError:
            pass
        assert d.has_errors()
        assert d.errors[0].stage == Stage.LOAD

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


class TestFindImportTarget:
    def test_loose_script(self, tmp_path):
        from stubpy.analysis.loader import find_import_target
        (tmp_path / "s.py").write_text("")
        assert find_import_target(tmp_path / "s.py") is None

    def test_package_module_and_init(self, tmp_path):
        from stubpy.analysis.loader import find_import_target
        pkg = tmp_path / "ldpkg" / "sub"
        pkg.mkdir(parents=True)
        for f in (tmp_path / "ldpkg" / "__init__.py", pkg / "__init__.py", pkg / "m.py"):
            f.write_text("")
        assert find_import_target(pkg / "m.py") == (tmp_path, "ldpkg.sub.m")
        assert find_import_target(pkg / "__init__.py") == (tmp_path, "ldpkg.sub")

    def test_namespace_dirs_only_below_explicit_root(self, tmp_path):
        from stubpy.analysis.loader import find_import_target
        (tmp_path / "ns" / "inner").mkdir(parents=True)
        (tmp_path / "ns" / "inner" / "__init__.py").write_text("")
        (tmp_path / "ns" / "inner" / "m.py").write_text("")
        assert find_import_target(tmp_path / "ns" / "inner" / "m.py") == (tmp_path / "ns", "inner.m")
        assert find_import_target(tmp_path / "ns" / "inner" / "m.py", root=tmp_path) == (tmp_path, "ns.inner.m")

    def test_src_dir_is_a_root(self, tmp_path):
        from stubpy.analysis.loader import find_import_target
        pkg = tmp_path / "src" / "srcpkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        assert find_import_target(pkg / "__init__.py", root=tmp_path) == (tmp_path / "src", "srcpkg")


class TestModuleLoader:
    def test_loads_once_and_cleans_up(self, tmp_path):
        import sys

        from stubpy.analysis.loader import ModuleLoader
        pkg = tmp_path / "ldpkg_once"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from . import a\n")
        (pkg / "a.py").write_text("from .b import X\n")
        (pkg / "b.py").write_text("X = 1\n")
        with ModuleLoader(pkg) as loader:
            first = loader.load(pkg / "a.py")
            assert loader.load(pkg / "a.py") is first
            assert first.name == "ldpkg_once.a" and first.module.X == 1
            assert str(tmp_path) not in sys.path
        assert not any(name.startswith("ldpkg_once") for name in sys.modules)

    def test_system_exit_becomes_module_load_error(self, tmp_path):
        import pytest

        from stubpy.analysis.loader import ModuleLoader, ModuleLoadError
        (tmp_path / "quits.py").write_text("raise SystemExit(4)\n")
        with ModuleLoader() as loader, pytest.raises(ModuleLoadError, match="SystemExit: 4"):
            loader.load(tmp_path / "quits.py")

    def test_failed_parent_package_fails_fast(self, tmp_path):
        import pytest

        from stubpy.analysis.loader import ModuleLoader, ModuleLoadError
        pkg = tmp_path / "ldpkg_bad"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("raise ValueError('nope')\n")
        (pkg / "m.py").write_text("")
        with ModuleLoader(pkg) as loader:
            with pytest.raises(ValueError):
                loader.load(pkg / "__init__.py")
            with pytest.raises(ModuleLoadError, match="ldpkg_bad failed to import: ValueError: nope"):
                loader.load(pkg / "m.py")
