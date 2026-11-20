"""Submodules held as attributes of one extension (pybind11 ``def_submodule``): a stub package and ``-m pkg.sub``."""
from __future__ import annotations

import importlib.machinery
import types
from pathlib import Path

import pytest

import stubpy
from stubpy.analysis.loader import LoadedModule, ModuleLoader
from stubpy.core._submodules import attribute_submodules, member_stub

from .fakes import FakeBuiltin

NAME = "extsub_fake"


def _module(name: str, **members: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in members.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An extension file whose import gives ``extsub_fake`` with ``fft`` and ``fft.helpers`` attribute submodules."""
    path = tmp_path / (NAME + importlib.machinery.EXTENSION_SUFFIXES[0])
    path.write_bytes(b"")
    helpers = _module(f"{NAME}.fft.helpers", pad=FakeBuiltin("pad", "pad(n: int) -> int\n", module=f"{NAME}.fft.helpers"))
    fft = _module(f"{NAME}.fft", helpers=helpers,
                  forward=FakeBuiltin("forward", "forward(x: float) -> float\n", module=f"{NAME}.fft"))
    alias = _module("other.mod")
    top = _module(NAME, fft=fft, alias=alias, version=FakeBuiltin("version", "version() -> str\n", module=NAME))
    top.__file__ = str(path)
    original = ModuleLoader.load

    def load(self, filepath, diagnostics=None):
        if Path(filepath).resolve() == path.resolve():
            return LoadedModule(top, path, NAME)
        return original(self, filepath, diagnostics)

    monkeypatch.setattr(ModuleLoader, "load", load)
    monkeypatch.setitem(__import__("sys").modules, NAME, top)
    return path


def test_attribute_submodules_need_a_matching_name():
    top = _module("pkg", fft=_module("pkg.fft"), other=_module("elsewhere"), renamed=_module("pkg.fft"))
    assert attribute_submodules(top) == ["fft"]


def test_member_stub():
    assert member_stub(Path("out/pkg.pyi"), "fft.helpers").as_posix() == "out/pkg/fft/helpers.pyi"


def test_generate_writes_a_stub_package(extension, tmp_path):
    out = tmp_path / "out"
    report = stubpy.generate(extension, out)
    assert report.ok
    written = sorted(p.relative_to(out).as_posix() for p in report.written)
    assert written == [f"{NAME}/__init__.pyi", f"{NAME}/fft/__init__.pyi", f"{NAME}/fft/helpers.pyi"]
    init = (out / NAME / "__init__.pyi").read_text(encoding="utf-8")
    assert "from . import fft as fft" in init and "def version() -> str: ..." in init
    assert "alias" not in init
    fft = (out / NAME / "fft" / "__init__.pyi").read_text(encoding="utf-8")
    assert "from . import helpers as helpers" in fft and "def forward(x: float) -> float: ..." in fft
    assert "def pad(n: int) -> int: ..." in (out / NAME / "fft" / "helpers.pyi").read_text(encoding="utf-8")


def test_check_compares_every_submodule(extension, tmp_path):
    out = tmp_path / "out"
    assert len(stubpy.check(extension, out).stale) == 3
    stubpy.generate(extension, out)
    assert stubpy.check(extension, out).ok


def test_render_dotted_submodule(extension):
    result = stubpy.render(f"{NAME}.fft.helpers")
    assert result.ok and result.module_name == f"{NAME}.fft.helpers"
    assert "def pad(n: int) -> int: ..." in result.text


def test_generate_dotted_submodule(extension, tmp_path):
    out = tmp_path / "out"
    report = stubpy.generate(f"{NAME}.fft", out)
    assert report.ok
    assert sorted(p.relative_to(out).as_posix() for p in report.written) == [
        f"{NAME}/fft/__init__.pyi", f"{NAME}/fft/helpers.pyi"]


def test_unknown_dotted_submodule_is_not_found(extension):
    with pytest.raises(ModuleNotFoundError):
        stubpy.render(f"{NAME}.missing")
