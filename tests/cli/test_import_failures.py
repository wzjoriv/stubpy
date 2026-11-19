"""
A module whose import fails is always reported, and the summary counts the modules stubbed from source only.
"""
from __future__ import annotations

from pathlib import Path

import stubpy
from stubpy.cli import main
from stubpy.core.diagnostics import Diagnostic, Level, Stage
from stubpy.core.results import Report, StubResult
from tests.conftest import write_tree

FILES = {
    "fpkg/__init__.py": "",
    "fpkg/good.py": "def f(x: int) -> int: ...\n",
    "fpkg/bad.py": "import not_installed_dependency_xyz\n\ndef g(x: int) -> int: ...\n",
    "fpkg/worse.py": "raise RuntimeError('boom')\n\ndef h() -> None: ...\n",
}


def test_failed_imports_are_warned_and_counted(tmp_path, capsys):
    root = write_tree(tmp_path, FILES)
    assert main(["generate", str(root / "fpkg"), "-o", str(tmp_path / "out"), "--no-config"]) == 0
    captured = capsys.readouterr()
    assert captured.err.count("[WARNING] (load)") == 2
    assert "not_installed_dependency_xyz" in captured.err and "boom" in captured.err
    assert "2 modules stubbed from source only: import failed." in captured.out


def test_quiet_hides_the_warning_but_not_the_count(tmp_path, capsys):
    root = write_tree(tmp_path, FILES)
    main(["generate", str(root / "fpkg"), "-o", str(tmp_path / "out"), "--no-config", "-q"])
    assert "[WARNING]" not in capsys.readouterr().err


def test_render_prints_the_failed_import(tmp_path, capsys):
    root = write_tree(tmp_path, FILES)
    assert main(["render", str(root / "fpkg" / "bad.py"), "--no-config"]) == 0
    captured = capsys.readouterr()
    assert "Import failed" in captured.err and "def g(x: int) -> int: ..." in captured.out


def test_policy_blocked_imports_are_counted_separately(tmp_path):
    root = write_tree(tmp_path, FILES)
    report = stubpy.generate(root / "fpkg", tmp_path / "out", config=stubpy.Config(imports="stdlib"))
    assert "stubbed from source only: import blocked by the import policy." in report.summary()
    assert "import failed" not in report.summary()


def test_clean_runs_keep_the_short_summary():
    report = Report(results=[StubResult("x: int")], written=[Path("m.pyi")])
    assert report.summary() == "Generated 1 stub, 0 failed."


def test_result_lists_its_import_failures():
    other = Diagnostic(Level.WARNING, Stage.EMIT, "m", "something else")
    failed = Diagnostic(Level.WARNING, Stage.LOAD, "m.py", "Import failed: x replaces itself; stubbing from the source")
    result = StubResult("", (other, failed))
    assert result.import_failures == [failed] and not result.import_blocked
