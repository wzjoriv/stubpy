"""Extension-module files as targets: naming, folder discovery, import failures, hand-written stubs."""
from __future__ import annotations

import importlib.machinery
from pathlib import Path

import pytest

import stubpy
from stubpy.compiled.detect import is_current_abi, is_extension_file, module_stem
from stubpy.core.targets import stub_path
from stubpy.state.diagnostics import Level

FOREIGN = "_ext.cpython-399-fake.so"


@pytest.mark.parametrize(("name", "stem"), [
    ("_x.cp311-win_amd64.pyd", "_x"),
    ("_x.cpython-311-x86_64-linux-gnu.so", "_x"),
    ("_x.abi3.so", "_x"),
    ("_x.pyd", "_x"),
    ("mod.py", "mod"),
    ("_x.pyx", "_x"),
])
def test_module_stem(name, stem):
    assert module_stem(name) == stem


def test_stub_path():
    assert stub_path(Path("a/_x.cp311-win_amd64.pyd")) == Path("a/_x.pyi")
    assert stub_path(Path("a/b.py")) == Path("a/b.pyi")


def test_extension_detection():
    assert is_extension_file("x.pyd") and is_extension_file("x.cpython-311-darwin.so")
    assert not is_extension_file("x.py") and not is_extension_file("x.pyx")


def test_current_abi_is_exact():
    assert is_current_abi("_x" + importlib.machinery.EXTENSION_SUFFIXES[0])
    assert not is_current_abi(FOREIGN)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """``pkg/`` with a pure module and an extension built for another interpreter."""
    pkg = tmp_path / "pkg_ext_targets"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def f(x: int) -> int:\n    return x\n")
    (pkg / FOREIGN).write_bytes(b"not a real extension")
    return pkg


class TestFolderRun:
    def test_unimportable_extension_is_a_warning(self, package, tmp_path):
        report = stubpy.generate(package, tmp_path / "out")
        assert report.ok
        ext = next(r for r in report if r.source.name == FOREIGN)
        assert ext.output is None and ext.warnings and not ext.errors
        assert "another interpreter" in ext.warnings[0].message
        assert (tmp_path / "out" / "pkg_ext_targets" / "core.pyi").is_file()
        assert not (tmp_path / "out" / "pkg_ext_targets" / "_ext.pyi").exists()

    def test_named_extension_is_a_failure(self, package):
        result = stubpy.render(package / FOREIGN)
        assert not result.ok and "another interpreter" in result.errors[0].message

    def test_source_wins_over_extension_of_the_same_name(self, package, tmp_path):
        (package / "core.cpython-399-fake.so").write_bytes(b"")
        report = stubpy.generate(package, tmp_path / "out")
        assert [r.source.name for r in report if r.module_name.endswith("core")] == ["core.py"]

    def test_hand_written_stub_next_to_extension_is_kept(self, package):
        stub = package / "_ext.pyi"
        stub.write_text("# hand-written\n")
        report = stubpy.generate(package)
        kept = next(r for r in report if r.source.name == FOREIGN)
        assert kept.output is None and kept.diagnostics[0].level is Level.INFO
        assert stub.read_text() == "# hand-written\n"
        assert stubpy.check(package).ok
