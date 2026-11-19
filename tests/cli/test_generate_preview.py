"""``stubpy generate --dry-run`` / ``--diff``: preview the stubs a run would change."""
from __future__ import annotations

from stubpy.cli import main
from stubpy.merge import BEGIN_MARKER


def test_dry_run_writes_nothing(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("def f(x: int) -> int: ...\n")
    assert main([str(src), "--no-config", "--dry-run"]) == 0
    assert not (tmp_path / "m.pyi").exists()
    out = capsys.readouterr().out
    assert "would write" in out and "m.pyi" in out and "1 stub(s) would change" in out


def test_diff_shows_the_change_and_writes(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("def f(x: int) -> int: ...\n")
    assert main([str(src), "--no-config"]) == 0
    src.write_text("def f(x: str) -> int: ...\n")
    capsys.readouterr()
    assert main([str(src), "--no-config", "--diff"]) == 0
    out = capsys.readouterr().out
    assert "-def f(x: int) -> int: ..." in out and "+def f(x: str) -> int: ..." in out
    assert "x: str" in (tmp_path / "m.pyi").read_text()


def test_incremental_dry_run_diff_shows_only_the_region(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("a: int = 1\n")
    assert main([str(src), "--no-config", "--incremental"]) == 0
    stub = tmp_path / "m.pyi"
    stub.write_text("# mine\n" + stub.read_text())
    src.write_text("a: str = ''\n")
    capsys.readouterr()
    assert main([str(src), "--no-config", "--incremental", "--dry-run", "--diff"]) == 0
    out = capsys.readouterr().out
    assert "-a: int" in out and "+a: str" in out and "# mine" not in out.replace(" # mine", "")
    assert stub.read_text().startswith(f"# mine\n{BEGIN_MARKER}\na: int")
