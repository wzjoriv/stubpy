"""--prune: stubs that no module produced are removed (generate) or reported (check); git-tracked ones stay."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stubpy import Config, check, generate

CFG = Config(imports="none", prune=True)


def _package(root: Path) -> Path:
    pkg = root / "pkg"
    (pkg / "shapes").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "shapes" / "__init__.py").write_text("")
    (pkg / "shapes" / "_circle.py").write_text("def circle(r: float) -> None: ...\n")
    return pkg


@pytest.mark.parametrize("in_place", [True, False])
def test_orphans_removed_and_reported(tmp_path, in_place):
    pkg = _package(tmp_path)
    out = None if in_place else tmp_path / "out"
    generate(pkg, out, config=Config(imports="none"))
    stub_dir = pkg / "shapes" if in_place else out / "pkg" / "shapes"
    orphan = stub_dir / "_basic.pyi"
    orphan.write_text("def circle(radius: int) -> None: ...\n")

    report = check(pkg, out, config=CFG)
    assert report.pruned == [orphan.resolve()] and not report.ok and orphan.exists()
    assert "1 orphan stub." in report.summary()

    report = generate(pkg, out, config=CFG)
    assert report.pruned == [orphan.resolve()] and not orphan.exists()
    assert (stub_dir / "_circle.pyi").exists()
    assert check(pkg, out, config=CFG).ok


def test_off_by_default(tmp_path):
    pkg = _package(tmp_path)
    generate(pkg, config=Config(imports="none"))
    orphan = pkg / "shapes" / "_basic.pyi"
    orphan.write_text("x: int\n")
    assert generate(pkg, config=Config(imports="none")).pruned == []
    assert orphan.exists()


@pytest.mark.skipif(shutil.which("git") is None or sys.platform == "emscripten", reason="git cannot run")
def test_git_tracked_stub_is_kept(tmp_path):
    pkg = _package(tmp_path)
    handwritten = pkg / "shapes" / "_native.pyi"
    handwritten.write_text("def fast() -> None: ...\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", str(handwritten)], cwd=tmp_path, check=True)
    report = generate(pkg, config=CFG)
    assert handwritten.exists() and report.pruned == []


def test_git_unrunnable_outside_repository_still_prunes(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    generate(pkg, config=Config(imports="none"))
    orphan = pkg / "shapes" / "_basic.pyi"
    orphan.write_text("x: int\n")

    def no_processes(*args, **kwargs):
        raise OSError(138, "processes unsupported")

    monkeypatch.setattr("stubpy.core._prune.subprocess.run", no_processes)
    monkeypatch.setattr("stubpy.core._prune._inside_repository", lambda folder: False)
    assert generate(pkg, config=CFG).pruned == [orphan.resolve()]
    monkeypatch.setattr("stubpy.core._prune._inside_repository", lambda folder: True)
    orphan.write_text("x: int\n")
    assert generate(pkg, config=CFG).pruned == [] and orphan.exists()
