"""Modules imported from a zip archive (``zipimport``; Pyodide keeps its standard library in one)."""
import ast
import sys
import zipfile

import pytest

import stubpy
from stubpy.analysis import vfs


@pytest.fixture
def archive(tmp_path, monkeypatch):
    path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("zpkg/__init__.py", "from .core import Canvas\n\n__all__ = ['Canvas', 'VERSION']\nVERSION = '1.0'\n")
        zf.writestr("zpkg/core.py", "class Canvas:\n    def draw(self, scale: float = 1.0) -> None: ...\n")
        zf.writestr("zpkg/sub/__init__.py", "")
        zf.writestr("zpkg/sub/deep.py", "# -*- coding: latin-1 -*-\nNAME = 'caf\xe9'\n".encode("latin-1"))
        zf.writestr("zmod.py", "def area(w: int, h: int) -> int:\n    return w * h\n")
    monkeypatch.syspath_prepend(str(path))
    yield path
    for name in [n for n in sys.modules if n == "zmod" or n.split(".")[0] == "zpkg"]:
        sys.modules.pop(name, None)


def test_vfs_answers_for_members(archive):
    assert vfs.is_file(archive / "zpkg" / "core.py") and vfs.is_dir(archive / "zpkg" / "sub")
    assert not vfs.exists(archive / "zpkg" / "missing.py")
    assert sorted(p.name for p in vfs.files_under(archive / "zpkg")) == ["__init__.py", "__init__.py", "core.py",
                                                                          "deep.py"]
    assert "café" in vfs.read_source(archive / "zpkg" / "sub" / "deep.py")


@pytest.mark.parametrize("mode", ["runtime", "ast"])
def test_render_module_from_archive(archive, mode):
    result = stubpy.render("zmod", config=stubpy.Config(mode=mode))
    assert result.ok, result.diagnostics
    assert result.text == "def area(w: int, h: int) -> int: ...\n"
    assert result.source == archive / "zmod.py"


@pytest.mark.parametrize("mode", ["runtime", "ast"])
def test_generate_folder_from_archive(archive, tmp_path, mode):
    out = tmp_path / f"stubs_{mode}"
    report = stubpy.generate("zpkg", out, config=stubpy.Config(mode=mode))
    assert report.ok, report.summary()
    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.pyi"))
    assert written == ["zpkg/__init__.pyi", "zpkg/core.pyi", "zpkg/sub/__init__.pyi", "zpkg/sub/deep.pyi"]
    for stub in out.rglob("*.pyi"):
        ast.parse(stub.read_text(encoding="utf-8"))
    assert "def draw(self, scale: float = 1.0) -> None: ..." in (out / "zpkg" / "core.pyi").read_text(encoding="utf-8")
    assert "from .core import Canvas as Canvas" in (out / "zpkg" / "__init__.pyi").read_text(encoding="utf-8")
    assert stubpy.check("zpkg", out, config=stubpy.Config(mode=mode)).ok


def test_generate_in_place_needs_an_output(archive):
    with pytest.raises(ValueError, match="inside an archive"):
        stubpy.generate("zmod")
