"""Real-corpus cases in ``corpora/rasterlib``: third-party wrappers, a broken parent, multi-platform builds."""
from __future__ import annotations

import importlib.machinery
import shutil
import sys
from pathlib import Path

import pytest

import stubpy

PACKAGE = Path(__file__).resolve().parents[2] / "corpora" / "rasterlib" / "rasterlib"
OTHER_PLATFORMS = (
    ".cp38-win32.pyd",
    ".cp39-win_arm64.pyd",
    ".cpython-39-x86_64-linux-gnu.so",
    ".cpython-310-aarch64-linux-gnu.so",
    ".cpython-313-darwin.so",
    ".abi3.so",
    ".pypy39-pp73-x86_64-linux-gnu.so",
)


def _imports() -> bool:
    """True when ``rasterlib.raster`` imports from the corpus folder, which needs every extension built."""
    saved = {n: m for n, m in sys.modules.items() if n == "rasterlib" or n.startswith("rasterlib.")}
    sys.path.insert(0, str(PACKAGE.parent))
    try:
        importlib.import_module("rasterlib.raster.levels")
        return True
    except Exception:
        return False
    finally:
        sys.path.remove(str(PACKAGE.parent))
        for name in [n for n in sys.modules if n == "rasterlib" or n.startswith("rasterlib.")]:
            del sys.modules[name]
        sys.modules.update(saved)


IMPORTS = _imports()


def _built(stem: str) -> Path | None:
    return next((PACKAGE / f"{stem}{s}" for s in importlib.machinery.EXTENSION_SUFFIXES
                 if (PACKAGE / f"{stem}{s}").is_file()), None)


@pytest.fixture(scope="module")
def stubs(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("rasterlib-additions")
    stubpy.generate(PACKAGE, out)
    return out / "rasterlib"


def _def(text: str, name: str) -> str:
    start = text.index(f"def {name}(")
    return text[start:text.index(": ...", start)]


def _levels(stubs: Path, name: str) -> str:
    return _def((stubs / "raster" / "levels.pyi").read_text(encoding="utf-8"), name)


@pytest.mark.skipif(not IMPORTS, reason="rasterlib does not import on this interpreter")
def test_numpy_clip_wrapper_expands_to_the_third_party_signature(stubs):
    clamp = _levels(stubs, "clamp")
    assert "coverage: ndarray" in clamp and "lo: float = 0.0" in clamp and "hi: float = 1.0" in clamp
    assert "out=None" in clamp and "min=..." in clamp and "max=..." in clamp
    assert clamp.count("**kwargs") == 1


@pytest.mark.skipif(not IMPORTS, reason="rasterlib does not import on this interpreter")
def test_numpy_asarray_wrapper_expands_from_a_builtin_signature(stubs):
    as_coverage = _levels(stubs, "as_coverage")
    for part in ("values,", "*,", "dtype=None", "order=None", "copy: bool | None = None", "like=None"):
        assert part in as_coverage
    assert "**kwargs" not in as_coverage


@pytest.mark.skipif(not IMPORTS, reason="rasterlib does not import on this interpreter")
def test_ufunc_wrapper_expands_from_a_ufunc(stubs):
    scale = _levels(stubs, "scale")
    assert "factor: float" in scale and "where: bool = True" in scale and "casting: str = 'same_kind'" in scale
    assert "**kwargs" not in scale


@pytest.mark.skipif(IMPORTS, reason="rasterlib imports, so the wrappers expand")
def test_wrappers_keep_kwargs_when_the_package_cannot_import(stubs):
    assert "**kwargs" in _levels(stubs, "clamp")
    assert "def as_coverage(values, **kwargs) -> np.ndarray" in _levels(stubs, "as_coverage")
    assert "**kwargs" in _levels(stubs, "scale")


@pytest.fixture(scope="module")
def plugins_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("rasterlib-plugins")
    return stubpy.generate(PACKAGE / "plugins", out), out


def test_broken_parent_package_falls_back_to_source(plugins_report):
    report, out = plugins_report
    assert report.ok
    by_name = {r.source.name: r for r in report}
    init = by_name["__init__.py"]
    assert any("No module named 'rasterlib_gpu'" in d.message for d in init.warnings)
    assert "DEVICE" not in init.text
    gamma = by_name["gamma.py"]
    assert gamma.ok
    assert any("rasterlib.plugins failed to import" in d.message for d in gamma.warnings)
    assert "def gamma_table(gamma: float = ..., size: int = 256) -> np.ndarray: ..." in gamma.text
    assert "DEFAULT_GAMMA: float" in gamma.text and "class GammaCurve:" in gamma.text


def test_broken_parent_does_not_leak_into_sys_modules(plugins_report):
    assert "rasterlib.plugins" not in sys.modules


def test_broken_parent_stubs_alongside_a_native_sibling(tmp_path):
    built = _built("_geometry")
    if built is None:
        pytest.skip("rasterlib is not built for this interpreter")
    folder = tmp_path / "rasterlib" / "plugins"
    shutil.copytree(PACKAGE / "plugins", folder)
    shutil.copy(built, folder / built.name)
    report = stubpy.generate(folder, tmp_path / "out")
    assert report.ok
    native = next(r for r in report if r.source.name == built.name)
    assert native.ok and native.text
    assert any(r.source.name == "gamma.py" and r.text for r in report)


@pytest.fixture
def multi_platform(tmp_path):
    built = _built("_pattern")
    if built is None:
        pytest.skip("rasterlib is not built for this interpreter")
    pkg = tmp_path / "rasterlib"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    shutil.copy(PACKAGE / "_pattern.pyx", pkg / "_pattern.pyx")
    shutil.copy(built, pkg / built.name)
    fakes = []
    for suffix in OTHER_PLATFORMS:
        if suffix not in importlib.machinery.EXTENSION_SUFFIXES:
            fake = pkg / f"_pattern{suffix}"
            fake.write_bytes(b"not a real extension")
            fakes.append(fake)
    saved = {n: m for n, m in sys.modules.items() if n == "rasterlib" or n.startswith("rasterlib.")}
    for name in saved:
        del sys.modules[name]
    yield pkg, built, fakes
    for name in [n for n in sys.modules if n == "rasterlib" or n.startswith("rasterlib.")]:
        del sys.modules[name]
    sys.modules.update(saved)


def test_picks_the_build_for_the_running_interpreter(multi_platform, tmp_path):
    pkg, built, fakes = multi_platform
    assert fakes
    report = stubpy.generate(pkg, tmp_path / "out")
    assert report.ok, report.summary()
    sources = [r.source.name for r in report]
    assert sources.count(built.name) == 1
    assert not any(f.name in sources for f in fakes)
    assert len([n for n in sources if n.startswith("_pattern")]) == 1
    assert [p.name for p in (tmp_path / "out" / "rasterlib").glob("_pattern*")] == ["_pattern.pyi"]


def test_pyx_still_supplies_the_cython_types(multi_platform, tmp_path):
    pkg, built, _ = multi_platform
    text = stubpy.render(pkg / built.name).text
    assert "def pattern_fill(" in text and "bilinear: bool = True" in text
    assert "out: Buffer" in text and "def set_num_threads(n: int) -> None: ..." in text
