"""Each source file is parsed once per run; the kept parse facts follow the file and are released."""
from __future__ import annotations

from stubpy import generate
from stubpy.config import Config
from stubpy.core import pipeline
from stubpy.core._requested import requested_names
from stubpy.resolve.static import SourceIndex
from stubpy.state.context import StubContext

NO_IMPORT = Config(imports="none")


def _hub(tmp_path, users=12):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "hub.py").write_text("".join(f"_p{i}: int = {i}\n" for i in range(users)))
    for i in range(users):
        (pkg / f"user{i}.py").write_text(f"from .hub import _p{i}\n")
    return pkg


def test_module_imported_by_many_keeps_every_requested_name(tmp_path):
    _hub(tmp_path)
    generate(tmp_path / "pkg", tmp_path / "out", config=NO_IMPORT)
    text = (tmp_path / "out/pkg/hub.pyi").read_text()
    assert all(f"_p{i}: int" in text for i in range(12))


def test_run_parses_each_file_once(tmp_path, monkeypatch):
    _hub(tmp_path, users=3)
    calls = []
    real = pipeline._parse
    monkeypatch.setattr(pipeline, "_parse", lambda *a: calls.append(a[1]) or real(*a))
    report = generate(tmp_path / "pkg", tmp_path / "out", config=NO_IMPORT)
    assert report.ok and calls == []


def test_parse_facts_released_after_render(tmp_path):
    pkg = _hub(tmp_path, users=2)
    index = SourceIndex()
    files = sorted(pkg.glob("*.py"))
    requested_names(files, index)
    hub = (pkg / "hub.py").resolve()
    assert hub in index.parsed
    pipeline.render_module(hub, StubContext(config=NO_IMPORT, source_index=index))
    assert hub not in index.parsed


def test_file_rewritten_after_the_scan_is_parsed_again(tmp_path):
    pkg = _hub(tmp_path, users=1)
    index = SourceIndex()
    requested_names(sorted(pkg.glob("*.py")), index)
    (pkg / "user0.py").write_text("from .hub import _p0\ndef added(x: int) -> int: ...\n")
    text = pipeline.render_module(pkg / "user0.py", StubContext(config=NO_IMPORT, source_index=index))
    assert "def added(x: int) -> int: ..." in text


def test_file_rewritten_between_runs(tmp_path):
    pkg = _hub(tmp_path, users=1)
    generate(pkg, tmp_path / "out", config=NO_IMPORT)
    (pkg / "hub.py").write_text("_p0: str = 'x'\n")
    generate(pkg, tmp_path / "out", config=NO_IMPORT)
    assert "_p0: str" in (tmp_path / "out/pkg/hub.pyi").read_text()


def test_same_named_modules_get_their_own_parse(tmp_path):
    for name, value in (("a", "1"), ("b", "'s'")):
        pkg = tmp_path / name
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "mod.py").write_text(f"X = {value}\n")
    generate(tmp_path, tmp_path / "out", config=NO_IMPORT)
    assert "X: int" in (tmp_path / "out/a/mod.pyi").read_text()
    assert "X: str" in (tmp_path / "out/b/mod.pyi").read_text()


def test_unparsable_file_still_reports_its_error(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "bad.py").write_text("def broken(:\n")
    report = generate(pkg, tmp_path / "out", config=NO_IMPORT)
    assert any("does not parse" in str(d) for r in report.results for d in r.diagnostics)
