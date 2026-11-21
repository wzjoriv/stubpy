"""An extension module still stubs when its parent package fails to import, and falls back to its ``.pyx``."""
from __future__ import annotations

import importlib.machinery
import shutil
import sys
from pathlib import Path

import pytest

import stubpy

RASTER = Path(__file__).resolve().parents[2] / "corpora" / "rasterlib" / "rasterlib"


def _built(stem: str) -> Path | None:
    return next((RASTER / f"{stem}{s}" for s in importlib.machinery.EXTENSION_SUFFIXES
                 if (RASTER / f"{stem}{s}").is_file()), None)


@pytest.fixture
def broken(tmp_path):
    """``brokenpkg/core/`` with a raising ``__init__`` above it; returns the ``core`` folder."""
    core = tmp_path / "brokenpkg" / "core"
    core.mkdir(parents=True)
    (tmp_path / "brokenpkg" / "__init__.py").write_text("raise RuntimeError('mid-refactor')\n")
    (core / "__init__.py").write_text("")
    yield core
    for name in [m for m in sys.modules if m == "brokenpkg" or m.startswith("brokenpkg.")]:
        sys.modules.pop(name, None)


@pytest.mark.skipif(_built("_scanline") is None, reason="rasterlib is not built for this interpreter")
def test_extension_loads_under_placeholder_parents(broken):
    built = _built("_scanline")
    shutil.copy(built, broken / built.name)
    report = stubpy.generate(broken, broken.parent.parent / "out")
    result = next(r for r in report if r.source.name == built.name)
    assert result.ok, result.diagnostics
    assert "def polygon_area(points, /): ..." in result.text
    assert any("loaded brokenpkg.core._scanline on its own" in d.message for d in result.warnings)
    assert "brokenpkg" not in sys.modules
    assert any(r.source.name == "__init__.py" and r.warnings for r in report)


def test_unloadable_extension_falls_back_to_its_pyx(broken):
    fake = broken / f"_shapes{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    fake.write_bytes(b"not a real extension")
    (broken / "_shapes.pyx").write_text("def area(double w, double h=1.0):\n    return w * h\n")
    result = stubpy.render(fake)
    assert result.ok, result.diagnostics
    assert "def area(w: float, h: float = 1.0): ..." in result.text
    assert any("stubbing from _shapes.pyx" in d.message for d in result.warnings)
