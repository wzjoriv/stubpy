"""Tests for stubpy.core.targets: target detection and stub-path planning."""
from __future__ import annotations

import sys

import pytest

from stubpy.config import Config
from stubpy.core.targets import plan_jobs, resolve_module_file, resolve_targets
from tests.conftest import write_tree


@pytest.fixture
def project(tmp_path):
    return write_tree(tmp_path, {
        "src/tgtpkg/__init__.py": "",
        "src/tgtpkg/a.py": "",
        "src/tgtpkg/sub/__init__.py": "",
        "src/tgtpkg/sub/b.py": "",
        "src/tgtpkg/tests/test_a.py": "",
        "scripts/run.py": "",
        "notes.txt": "",
    })


class TestResolveTargets:
    def test_file(self, project):
        (t,) = resolve_targets(str(project / "scripts" / "run.py"), Config())
        assert not t.is_dir and t.anchor == project / "scripts"

    def test_package_folder_anchor_is_import_root(self, project):
        (t,) = resolve_targets(project / "src" / "tgtpkg" / "sub", Config())
        assert t.is_dir and t.anchor == project / "src"

    def test_plain_folder_anchor_is_itself(self, project):
        (t,) = resolve_targets(project / "src", Config())
        assert t.anchor == project / "src"

    def test_glob_keeps_python_files_and_folders(self, project):
        found = resolve_targets(str(project / "*"), Config())
        assert sorted(t.path.name for t in found) == ["scripts", "src"]

    def test_dotted_names(self, project, monkeypatch):
        monkeypatch.syspath_prepend(str(project / "src"))
        (pkg,) = resolve_targets("tgtpkg", Config())
        (mod,) = resolve_targets("tgtpkg.sub.b", Config())
        assert pkg.is_dir and pkg.path == project / "src" / "tgtpkg"
        assert mod.path == project / "src" / "tgtpkg" / "sub" / "b.py"
        assert "tgtpkg" not in sys.modules and "tgtpkg.sub" not in sys.modules

    def test_existing_path_wins_over_module_name(self, project, monkeypatch):
        monkeypatch.chdir(project)
        (t,) = resolve_targets("scripts", Config())
        assert t.path == project / "scripts"

    def test_config_modules_always_dotted(self, project, monkeypatch):
        monkeypatch.syspath_prepend(str(project / "src"))
        monkeypatch.chdir(project)
        (t,) = resolve_targets(None, Config(modules=["tgtpkg.a"]))
        assert t.path.name == "a.py"

    def test_errors(self, project):
        with pytest.raises(FileNotFoundError, match="No such file, folder or module"):
            resolve_targets("missing/thing.py", Config())
        with pytest.raises(ValueError, match="not a Python source"):
            resolve_targets(project / "notes.txt", Config())
        with pytest.raises(TypeError):
            resolve_targets([42], Config())  # type: ignore[list-item]
        with pytest.raises(ValueError, match="No target"):
            resolve_targets([], Config())

    def test_resolve_module_file(self, project):
        assert resolve_module_file(project / "src" / "tgtpkg").name == "__init__.py"


class TestPlanJobs:
    def test_next_to_source(self, project):
        plan = plan_jobs(resolve_targets(project / "src" / "tgtpkg", Config()), None, Config())
        jobs = [j for _, js in plan.groups for j in js]
        assert all(j.output == j.source.with_suffix(".pyi") for j in jobs)
        assert plan.placeholders == []

    def test_exclude_is_relative_to_the_folder(self, project):
        cfg = Config(exclude=["tests/*"])
        plan = plan_jobs(resolve_targets(project / "src" / "tgtpkg", cfg), project / "out", cfg)
        names = sorted(j.output.relative_to(project / "out").as_posix() for _, js in plan.groups for j in js)
        assert names == ["tgtpkg/__init__.pyi", "tgtpkg/a.pyi", "tgtpkg/sub/__init__.pyi", "tgtpkg/sub/b.pyi"]

    def test_placeholder_for_folder_without_stub(self, project):
        cfg = Config(exclude=["**/__init__.py", "__init__.py"])
        plan = plan_jobs(resolve_targets(project / "src" / "tgtpkg", cfg), project / "out", cfg)
        placeholders = sorted(j.output.relative_to(project / "out").as_posix() for j in plan.placeholders)
        assert placeholders == ["tgtpkg/__init__.pyi", "tgtpkg/sub/__init__.pyi"]

    def test_one_loader_root_per_folder_target(self, project):
        targets = resolve_targets([project / "src" / "tgtpkg", project / "scripts" / "run.py"], Config())
        roots = [root for root, _ in plan_jobs(targets, None, Config()).groups]
        assert roots == [project / "src" / "tgtpkg", None]
