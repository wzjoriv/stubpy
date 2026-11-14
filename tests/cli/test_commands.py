"""The generate / check / render sub-commands, config handling and exit codes."""
from __future__ import annotations

import pytest

from stubpy import __version__
from stubpy.cli import main
from stubpy.cli.parser import with_default_command


@pytest.fixture
def pkg(tmp_path):
    """A package ``clipkg`` with two modules, and the folder that holds it."""
    root = tmp_path / "proj"
    p = root / "clipkg"
    p.mkdir(parents=True)
    (p / "__init__.py").write_text("")
    (p / "a.py").write_text("def f(x: int) -> str: ...\n")
    (p / "b.py").write_text("Y: int = 1\n")
    return p


class TestDefaultCommand:
    @pytest.mark.parametrize("argv, expected", [
        ([], ["generate"]),
        (["mod.py"], ["generate", "mod.py"]),
        (["--mode", "ast", "x"], ["generate", "--mode", "ast", "x"]),
        (["check", "x"], ["check", "x"]),
        (["render", "x"], ["render", "x"]),
        (["generate", "x"], ["generate", "x"]),
        (["--version"], ["--version"]),
        (["-h"], ["-h"]),
    ])
    def test_prefix(self, argv, expected):
        assert with_default_command(argv) == expected

    def test_bare_file_and_explicit_generate_agree(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("X: int = 1\n")
        assert main([str(src)]) == 0
        bare = src.with_suffix(".pyi").read_text()
        assert main(["generate", str(src)]) == 0
        assert src.with_suffix(".pyi").read_text() == bare


class TestVersionAndUsage:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert capsys.readouterr().out.strip() == f"stubpy {__version__}"

    def test_bad_choice_is_exit_2(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            main([str(tmp_path), "--mode", "ast_only"])
        assert exc.value.code == 2

    def test_render_needs_a_target(self):
        with pytest.raises(SystemExit) as exc:
            main(["render"])
        assert exc.value.code == 2

    def test_unknown_target_is_exit_2(self, tmp_path, capsys):
        assert main([str(tmp_path / "missing.py")]) == 2
        assert "stubpy: error:" in capsys.readouterr().err

    def test_no_targets_and_no_config_is_exit_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert main([]) == 2
        assert "No target" in capsys.readouterr().err

    def test_invalid_config_is_exit_2(self, tmp_path, capsys):
        (tmp_path / "stubpy.toml").write_text('union_style = "fancy"\n')
        (tmp_path / "m.py").write_text("")
        assert main([str(tmp_path / "m.py")]) == 2
        assert "union_style" in capsys.readouterr().err


class TestGenerate:
    def test_reports_written_and_summary(self, pkg, tmp_path, capsys):
        out = tmp_path / "stubs"
        assert main([str(pkg), "-o", str(out)]) == 0
        printed = capsys.readouterr().out
        assert "wrote" in printed
        assert printed.strip().endswith("Generated 3 stubs, 0 failed.")
        assert (out / "clipkg" / "a.pyi").exists()

    def test_quiet(self, pkg, tmp_path, capsys):
        assert main([str(pkg), "-o", str(tmp_path / "stubs"), "-q"]) == 0
        assert capsys.readouterr().out == ""

    def test_failure_is_exit_1(self, pkg, tmp_path, capsys):
        (pkg / "bad.py").write_text("raise RuntimeError('kaput')\n")
        assert main([str(pkg), "-o", str(tmp_path / "stubs")]) == 1
        err = capsys.readouterr().err
        assert "FAILED" in err and "kaput" in err

    def test_strict_fails_on_warnings(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("sentinel = object()\n")
        assert main([str(src)]) == 0
        assert main([str(src), "--strict"]) == 1

    def test_uses_config_targets(self, pkg, monkeypatch, capsys):
        root = pkg.parent
        (root / "pyproject.toml").write_text('[tool.stubpy]\ntargets = ["clipkg"]\noutput_dir = "typings"\n')
        monkeypatch.chdir(root)
        assert main([]) == 0
        assert (root / "typings" / "clipkg" / "a.pyi").exists()

    def test_uses_config_modules(self, pkg, monkeypatch):
        root = pkg.parent
        (root / "stubpy.toml").write_text('modules = ["clipkg.a"]\n')
        monkeypatch.chdir(root)
        monkeypatch.syspath_prepend(str(root))
        assert main([]) == 0
        assert (pkg / "a.pyi").exists()
        assert not (pkg / "b.pyi").exists()

    def test_flags_override_config(self, tmp_path):
        (tmp_path / "stubpy.toml").write_text("include_private = false\nmode = \"ast\"\n")
        src = tmp_path / "mod.py"
        src.write_text("def _p() -> None: ...\n")
        assert main([str(src), "--include-private"]) == 0
        assert "def _p" in src.with_suffix(".pyi").read_text()

    def test_dotted_module_target(self, pkg, monkeypatch, tmp_path):
        monkeypatch.syspath_prepend(str(pkg.parent))
        out = tmp_path / "stubs"
        assert main(["clipkg.b", "-o", str(out)]) == 0
        assert (out / "clipkg" / "b.pyi").exists()


class TestCheck:
    def test_up_to_date_is_exit_0(self, pkg, tmp_path, capsys):
        out = tmp_path / "stubs"
        main([str(pkg), "-o", str(out), "-q"])
        assert main(["check", str(pkg), "-o", str(out)]) == 0
        assert "0 stale" in capsys.readouterr().out

    def test_stale_is_exit_1(self, pkg, tmp_path, capsys):
        out = tmp_path / "stubs"
        main([str(pkg), "-o", str(out), "-q"])
        (pkg / "a.py").write_text("def f(x: int, y: int = 0) -> str: ...\n")
        assert main(["check", str(pkg), "-o", str(out)]) == 1
        printed = capsys.readouterr().out
        assert "stale" in printed and "a.pyi" in printed
        assert "---" not in printed

    def test_missing_stubs_are_stale(self, pkg, capsys):
        assert main(["check", str(pkg)]) == 1
        assert not (pkg / "a.pyi").exists()

    def test_diff(self, pkg, tmp_path, capsys):
        out = tmp_path / "stubs"
        main([str(pkg), "-o", str(out), "-q"])
        (pkg / "b.py").write_text("Y: str = 'now a string'\n")
        assert main(["check", str(pkg), "-o", str(out), "--diff"]) == 1
        printed = capsys.readouterr().out
        assert "--- a/" in printed and "+++ b/" in printed
        assert "-Y: int" in printed and "+Y: str" in printed

    def test_diff_for_missing_stub(self, pkg, tmp_path, capsys):
        assert main(["check", str(pkg / "b.py"), "--diff"]) == 1
        printed = capsys.readouterr().out
        assert "--- /dev/null" in printed
        assert "+Y: int" in printed

    def test_check_writes_nothing(self, pkg, tmp_path):
        out = tmp_path / "stubs"
        main(["check", str(pkg), "-o", str(out)])
        assert not out.exists()


class TestRender:
    def test_prints_stub(self, pkg, capsys):
        assert main(["render", str(pkg / "a.py")]) == 0
        printed = capsys.readouterr().out
        assert "def f(x: int) -> str: ..." in printed
        assert not (pkg / "a.pyi").exists()

    def test_dotted_name(self, pkg, monkeypatch, capsys):
        monkeypatch.syspath_prepend(str(pkg.parent))
        assert main(["render", "clipkg.b", "--mode", "ast"]) == 0
        assert "Y: int" in capsys.readouterr().out

    def test_failure_is_exit_1(self, tmp_path, capsys):
        src = tmp_path / "bad.py"
        src.write_text("raise RuntimeError('render-fail')\n")
        assert main(["render", str(src)]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "render-fail" in captured.err

    def test_folder_is_exit_2(self, tmp_path):
        assert main(["render", str(tmp_path)]) == 2
