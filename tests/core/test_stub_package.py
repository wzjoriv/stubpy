"""Stub-only distributions: layout, py.typed, pyproject and check."""
from __future__ import annotations

from pathlib import Path

import pytest

from stubpy import Config, check, generate

CFG = Config(imports="none", stub_package=True)


def _package(root: Path) -> Path:
    pkg = root / "src" / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("def f(x: int) -> int:\n    return x\n")
    (pkg / "sub" / "__init__.py").write_text("")
    (pkg / "sub" / "m.py").write_text("y: int = 1\n")
    return pkg


def test_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    report = generate(_package(tmp_path), out, config=CFG)
    dist = out / "pkg-stubs"
    assert report.ok and len(report.written) == 3
    assert sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file()) == [
        "pkg-stubs/__init__.pyi", "pkg-stubs/py.typed", "pkg-stubs/sub/__init__.pyi", "pkg-stubs/sub/m.pyi",
        "pyproject.toml",
    ]
    assert (dist / "pkg-stubs" / "py.typed").read_text() == "partial\n"
    meta = (dist / "pyproject.toml").read_text().splitlines()
    assert {'name = "pkg-stubs"', 'requires-python = ">=3.10"', 'packages = ["pkg-stubs", "pkg-stubs.sub"]'} <= set(meta)


def test_module(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("x: int = 1\n")
    generate(src, tmp_path / "out", config=CFG)
    assert (tmp_path / "out" / "mod-stubs" / "mod-stubs" / "__init__.pyi").read_text() == "x: int\n"


def test_check(tmp_path: Path) -> None:
    pkg, out = _package(tmp_path), tmp_path / "out"
    generate(pkg, out, config=CFG)
    assert check(pkg, out, config=CFG).ok
    (out / "pkg-stubs" / "pkg-stubs" / "py.typed").unlink()
    assert check(pkg, out, config=CFG).stale == [out.resolve() / "pkg-stubs" / "pkg-stubs" / "py.typed"]


def test_needs_output_folder(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text("x = 1\n")
    with pytest.raises(ValueError, match="output folder"):
        generate(src, config=CFG)
    with pytest.raises(ValueError, match="output folder"):
        generate(src, tmp_path / "mod.pyi", config=CFG)
