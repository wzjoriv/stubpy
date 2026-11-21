"""--typecheck: a checker's errors become WARNINGs on the stubs they belong to."""
from __future__ import annotations

from pathlib import Path

from stubpy import Config, Level, generate
from stubpy.core import _typecheck


def _package(root: Path) -> Path:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "good.py").write_text("x: int = 1\n")
    (pkg / "bad.py").write_text("import mod_missing\ny: mod_missing.Thing\n")
    return pkg


def test_errors_attach_to_their_stub(tmp_path, monkeypatch):
    out = tmp_path / "out"

    def fake(paths, version):
        bad = next(p for p in paths if p.name == "bad.pyi")
        return "mypy", [(bad, "2", 'Name "mod_missing.Thing" is not defined', "name-defined")]

    monkeypatch.setattr(_typecheck, "_run", fake)
    report = generate(_package(tmp_path), out, config=Config(imports="none", typecheck=True))
    warned = {r.output.name: [d for d in r.diagnostics if d.stage.value == "typecheck"] for r in report.results}
    assert [d.level for d in warned["bad.pyi"]] == [Level.WARNING]
    assert "line 2" in warned["bad.pyi"][0].message and not warned["good.pyi"]
    assert report.summary().endswith("1 type error in the stubs.")
    assert report.ok
    (tmp_path / "s").mkdir()
    strict = generate(_package(tmp_path / "s"), tmp_path / "s_out",
                      config=Config(imports="none", typecheck=True, strict=True))
    assert [r.output.name for r in strict.failed] == ["bad.pyi"]


def test_no_checker_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(_typecheck, "_run", lambda paths, version: None)
    report = generate(_package(tmp_path), tmp_path / "out", config=Config(imports="none", typecheck=True))
    assert "type check skipped" in report.summary()


def test_parse_mypy_and_pyright(tmp_path):
    mypy = _typecheck._parse("pkg/m.pyi:3: error: Bad  [misc]", _typecheck._MYPY_LINE, tmp_path)
    pyright = _typecheck._parse("  pkg/m.pyi:4:5 - error: Bad thing (reportGeneralTypeIssues)",
                                _typecheck._PYRIGHT_LINE, tmp_path)
    assert mypy[0][1:] == ("3", "Bad", "misc")
    assert pyright[0][1:] == ("4", "Bad thing", "reportGeneralTypeIssues")
    assert mypy[0][0] == (tmp_path / "pkg" / "m.pyi").resolve()
