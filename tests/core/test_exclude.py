"""What a folder run skips: default ``exclude`` patterns, ``<non-identifier>``, ``extend_exclude`` and explicit targets."""
from __future__ import annotations

import pytest

import stubpy
from stubpy import Config
from stubpy._constants import DEFAULT_EXCLUDE
from stubpy.cli import main
from stubpy.core._exclude import excluded_by
from tests.conftest import write_tree

ODD = {
    ".rug_controller.py": "def broken(:\n",
    ".rug___init__.py": "x = 1\n",
    "name copy.py": "def broken(:\n",
    "foo-bar.py": "x = 1\n",
    "2thing.py": "x = 1\n",
    "my folder/mod.py": "x = 1\n",
    "__pycache__/cached.py": "x = 1\n",
}


@pytest.fixture
def pkg(tmp_path):
    return write_tree(tmp_path / "src", {"oddpkg/__init__.py": "", "oddpkg/good.py": "def ok() -> int: ...\n",
                                         **{f"oddpkg/{k}": v for k, v in ODD.items()}}) / "oddpkg"


@pytest.mark.parametrize("rel, pattern", [
    (".rug_controller.py", ".*"),
    ("name copy.py", "<non-identifier>"),
    ("foo-bar.py", "<non-identifier>"),
    ("2thing.py", "<non-identifier>"),
    ("my folder/mod.py", "<non-identifier>"),
    ("__pycache__/cached.py", "__pycache__"),
    ("sub/build/x.py", "build"),
    ("mypkg.egg-info/x.py", "*.egg-info"),
    ("good.py", None),
    ("_native.cp311-win_amd64.pyd", None),
    ("sub/_private.py", None),
])
def test_default_patterns(rel, pattern):
    assert excluded_by(rel, DEFAULT_EXCLUDE) == pattern


def test_defaults_skip_odd_files_and_never_fail(pkg, tmp_path):
    report = stubpy.generate(pkg, tmp_path / "out")
    assert report.ok
    assert sorted(p.relative_to(tmp_path / "out").as_posix() for p in report.written) == [
        "oddpkg/__init__.pyi", "oddpkg/good.pyi"]
    assert {p.name for p, _ in report.excluded} == {
        ".rug_controller.py", ".rug___init__.py", "name copy.py", "foo-bar.py", "2thing.py", "mod.py", "cached.py"}
    assert stubpy.check(pkg, tmp_path / "out").ok


def test_empty_exclude_scans_everything_and_fails_cleanly(pkg, tmp_path):
    report = stubpy.generate(pkg, tmp_path / "out", config=Config(exclude=[]))
    assert {r.source.name for r in report.failed} == {".rug_controller.py", "name copy.py"}
    assert (tmp_path / "out" / "oddpkg" / "good.pyi").exists()
    assert report.excluded == []


def test_extend_exclude_keeps_the_defaults(pkg, tmp_path):
    report = stubpy.generate(pkg, tmp_path / "out", config=Config(extend_exclude=["good.py"]))
    assert report.ok and [p.name for p in report.written] == ["__init__.pyi"]
    assert ("good.py", "good.py") in {(p.name, pat) for p, pat in report.excluded}
    assert (".rug_controller.py", ".*") in {(p.name, pat) for p, pat in report.excluded}


def test_explicit_hidden_or_odd_target_is_stubbed(pkg):
    for name in (".rug___init__.py", "foo-bar.py"):
        report = stubpy.generate(pkg / name)
        assert report.ok, report.summary()
        assert (pkg / name).with_suffix(".pyi").read_text() == "x: int\n"


def test_cli_show_excluded_and_exclude_replaces(pkg, tmp_path, capsys):
    assert main([str(pkg), "-o", str(tmp_path / "out"), "--no-config", "--show-excluded"]) == 0
    out = capsys.readouterr().out
    assert "excluded" in out and "name copy.py (<non-identifier>)" in out
    assert main([str(pkg), "-o", str(tmp_path / "out2"), "--no-config", "--exclude", ".*", "--exclude", "* *",
                 "--exclude", "__pycache__"]) == 0
    assert (tmp_path / "out2" / "oddpkg" / "foo-bar.pyi").exists()
