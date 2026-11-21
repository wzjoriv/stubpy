"""Run cache: unchanged modules reuse their stub; a change to a module or its package imports re-renders it."""
from __future__ import annotations

from pathlib import Path

from stubpy import Config, generate
from stubpy.core import _cache


def _package(root: Path) -> Path:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "base.py").write_text("def f(x: int) -> int:\n    return x\n")
    (pkg / "user.py").write_text("from .base import f\n\ndef g(*args, **kwargs):\n    return f(*args, **kwargs)\n")
    (pkg / "other.py").write_text("y: int = 1\n")
    return pkg


def _run(pkg: Path, out: Path, cfg: Config, monkeypatch) -> list[str]:
    rendered: list[str] = []
    real = _cache.RunCache.put

    def put(self, key, result):
        rendered.append(result.source.name)
        real(self, key, result)

    monkeypatch.setattr(_cache.RunCache, "put", put)
    assert generate(pkg, out, config=cfg).ok
    return sorted(rendered)


def test_reuse_and_invalidate(tmp_path, monkeypatch):
    pkg, out = _package(tmp_path), tmp_path / "out"
    cfg = Config(imports="none", cache=True, cache_dir=str(tmp_path / "cache"))
    assert _run(pkg, out, cfg, monkeypatch) == ["__init__.py", "base.py", "other.py", "user.py"]
    first = (out / "pkg" / "user.pyi").read_text()
    assert _run(pkg, out, cfg, monkeypatch) == []
    assert (out / "pkg" / "user.pyi").read_text() == first

    (pkg / "base.py").write_text("def f(x: int, y: str = '') -> int:\n    return x\n")
    assert _run(pkg, out, cfg, monkeypatch) == ["base.py", "user.py"]
    assert "y: str" in (out / "pkg" / "user.pyi").read_text()


def test_other_options_start_empty(tmp_path, monkeypatch):
    pkg, out = _package(tmp_path), tmp_path / "out"
    cfg = Config(imports="none", cache=True, cache_dir=str(tmp_path / "cache"))
    _run(pkg, out, cfg, monkeypatch)
    legacy = Config(imports="none", cache=True, cache_dir=str(tmp_path / "cache"), union_style="legacy")
    assert len(_run(pkg, out, legacy, monkeypatch)) == 4


def test_off_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generate(_package(tmp_path), tmp_path / "out", config=Config(imports="none"))
    assert not (tmp_path / ".stubpy_cache").exists()
