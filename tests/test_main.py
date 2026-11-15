"""
tests/test_main.py
-------------------
Tests for :mod:`stubpy.__main__` — the CLI entry point.

Covers ``stubpy`` invoked with multiple files, directories, and flag
combinations.  Uses :func:`~stubpy.__main__.main` directly rather than
subprocess so tests are portable across all systems.
"""
from __future__ import annotations

import sys

from stubpy.__main__ import main


class TestCLIMultiFile:
    def test_two_files(self, tmp_path):
        """stubpy file1.py file2.py writes two stubs."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("def hello(name: str) -> str: ...")
        f2.write_text("def goodbye(name: str) -> None: ...")

        from stubpy.__main__ import main
        rc = main([str(f1), str(f2)])
        assert rc == 0
        assert (tmp_path / "a.pyi").exists()
        assert (tmp_path / "b.pyi").exists()

    def test_multi_file_output_flag_ignored_with_warning(self, tmp_path, capsys):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x: int = 1")
        f2.write_text("y: str = 'hi'")

        from stubpy.__main__ import main
        rc = main([str(f1), str(f2), "-o", str(tmp_path / "out")])
        assert rc == 0
        captured = capsys.readouterr()
        assert "ignored" in captured.err.lower()

    def test_single_file_mode_unchanged(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo(x: int) -> int: return x")
        from stubpy.__main__ import main
        rc = main([str(f)])
        assert rc == 0
        assert (tmp_path / "mod.pyi").exists()

    def test_mixed_file_and_dir(self, tmp_path):
        """Pass one file and one directory together."""
        # Create a sub-package
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "utils.py").write_text("def helper(x: int) -> int: ...")

        solo = tmp_path / "solo.py"
        solo.write_text("CONST: str = 'hello'")

        from stubpy.__main__ import main
        rc = main([str(solo), str(pkg)])
        assert rc == 0
        assert (tmp_path / "solo.pyi").exists()


class TestExcludeFlag:
    def test_exclude_single_pattern(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "public.py").write_text("X: int = 1\n")
        (pkg / "secret.py").write_text("SECRET: str = 'x'\n")
        out = tmp_path / "out"
        sys.argv = ["stubpy", str(pkg), "-o", str(out), "--exclude", "secret.py"]
        main()
        assert (out / "public.pyi").exists()
        assert not (out / "secret.pyi").exists()

    def test_exclude_multiple_patterns(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "keep.py").write_text("X: int = 1\n")
        (pkg / "skip_a.py").write_text("A: int = 1\n")
        (pkg / "skip_b.py").write_text("B: int = 1\n")
        out = tmp_path / "out"
        sys.argv = [
            "stubpy", str(pkg), "-o", str(out),
            "--exclude", "skip_a.py",
            "--exclude", "skip_b.py",
        ]
        main()
        assert (out / "keep.pyi").exists()
        assert not (out / "skip_a.pyi").exists()
        assert not (out / "skip_b.pyi").exists()

    def test_exclude_cli_extends_toml_config(self, tmp_path):
        """CLI --exclude patterns are appended to those from the config file."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("X: int = 1\n")
        (pkg / "b.py").write_text("Y: int = 1\n")
        (pkg / "c.py").write_text("Z: int = 1\n")
        # Config excludes 'a.py', CLI adds 'b.py'
        (pkg / "stubpy.toml").write_text('exclude = ["a.py"]\n')
        out = tmp_path / "out"
        sys.argv = ["stubpy", str(pkg), "-o", str(out), "--exclude", "b.py"]
        main()
        assert (out / "c.pyi").exists()
        assert not (out / "a.pyi").exists()
        assert not (out / "b.pyi").exists()


class TestNoRespectAllFlag:
    def test_stubs_hidden_class_when_flag_set(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "__all__ = ['Public']\n"
            "class Public: pass\n"
            "class Hidden: pass\n"
        )
        sys.argv = ["stubpy", str(src), "--no-respect-all"]
        main()
        content = src.with_suffix(".pyi").read_text()
        assert "Public" in content
        assert "Hidden" in content

    def test_respects_all_by_default(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "__all__ = ['Public']\n"
            "class Public: pass\n"
            "class Hidden: pass\n"
        )
        sys.argv = ["stubpy", str(src)]
        main()
        content = src.with_suffix(".pyi").read_text()
        assert "Public" in content
        assert "Hidden" not in content

    def test_no_all_declared_flag_has_no_effect(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class A: pass\nclass B: pass\n")
        sys.argv = ["stubpy", str(src), "--no-respect-all"]
        main()
        content = src.with_suffix(".pyi").read_text()
        assert "A" in content
        assert "B" in content


class TestNewCLIFlags:
    """CLI flags added in v0.6.1: --no-resolve-kwargs, --no-resolve-args,
    --execution-mode, --no-config."""

    def test_no_resolve_kwargs_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class B:\n    def __init__(self, x: int) -> None: ...\n\n"
            "class C(B):\n    def __init__(self, **kw) -> None: ...\n"
        )
        sys.argv = ["stubpy", str(src), "--no-resolve-kwargs"]
        main()
        stub = src.with_suffix(".pyi").read_text()
        c_part = stub.split("class C")[1]
        assert "**kw" in c_part
        assert "x: int" not in c_part

    def test_no_resolve_args_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def base(*items: str, gamma: float = 1.0) -> None: ...\n\n"
            "def caller(*items: str, **opts) -> None:\n    base(*items, **opts)\n"
        )
        sys.argv = ["stubpy", str(src), "--no-resolve-args"]
        main()
        stub = src.with_suffix(".pyi").read_text()
        caller_part = stub.split("def caller")[1]
        assert "*items" in caller_part

    def test_execution_mode_ast_only_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("X = 100\ndef f(x: int) -> str: ...\n")
        sys.argv = ["stubpy", str(src), "--execution-mode", "ast_only"]
        main()
        stub = src.with_suffix(".pyi").read_text()
        assert "def f" in stub
        assert "X: int" in stub  # variable inferred even in AST-only

    def test_no_config_ignores_toml(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "class A:\n    def f(self, x: int) -> None: ...\n\n"
            "class B(A):\n    def f(self, **kw) -> None: ...\n"
        )
        # stubpy.toml says resolve_kwargs=false — should be ignored with --no-config
        (tmp_path / "stubpy.toml").write_text("resolve_kwargs = false\n")
        sys.argv = ["stubpy", str(src), "--no-config"]
        main()
        stub = src.with_suffix(".pyi").read_text()
        b_part = stub.split("class B")[1]
        # Default behavior (resolve_kwargs=True) should apply
        assert "x: int" in b_part

    def test_execution_mode_auto_flag(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("X: int = 1\ndef f(a: int) -> str: ...\n")
        sys.argv = ["stubpy", str(src), "--execution-mode", "auto"]
        result = main()
        assert result == 0
        stub = src.with_suffix(".pyi").read_text()
        assert "def f" in stub
