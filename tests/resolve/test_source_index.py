"""SourceIndex run caches keep same-named modules of different packages apart."""
from __future__ import annotations

from stubpy import generate
from stubpy.config import Config, VersionBranches
from stubpy.resolve.static import SourceIndex


def _package(root, name, body):
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text(body)
    (pkg / "mod.py").write_text("from .helpers import Thing\n")
    return pkg


def test_relative_import_resolves_per_package(tmp_path):
    a = _package(tmp_path, "a", "class Thing: ...\n")
    b = _package(tmp_path, "b", "Thing = 1\n")
    index = SourceIndex()
    for pkg in (a, b):
        here = index.module_at(pkg / "mod.py")
        assert index.import_from(here, ".helpers").path == (pkg / "helpers.py").resolve()
    assert [c.name for c in index.module_at(a / "helpers.py").symbols.classes] == ["Thing"]
    assert index.module_at(b / "helpers.py").symbols.classes == []


def test_same_named_modules_requested_separately(tmp_path):
    _package(tmp_path, "a", "_one: int = 1\n")
    _package(tmp_path, "b", "_two: int = 2\n")
    for pkg, kept in (("a", "_one"), ("b", "_two")):
        (tmp_path / pkg / "mod.py").write_text(f"from .helpers import {kept}\n")
    generate(tmp_path, tmp_path / "out", config=Config(imports="none"))
    assert "_one" in (tmp_path / "out/a/helpers.pyi").read_text()
    assert "_two" not in (tmp_path / "out/a/helpers.pyi").read_text()
    assert "_two" in (tmp_path / "out/b/helpers.pyi").read_text()


def test_version_branches_not_taken_from_shared_harvest(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("import sys\nif sys.version_info >= (99,):\n    def f() -> int: ...\nelse:\n    def f() -> str: ...\n")
    generate(src, tmp_path / "out", config=Config(imports="none", version_branches=VersionBranches.EMIT))
    text = (tmp_path / "out/m.pyi").read_text()
    assert "-> int" in text and "-> str" in text
