"""Tests for CLI glob expansion."""
from __future__ import annotations


class TestCLIGlob:
    def test_quoted_glob_expands(self, tmp_path):
        """stubpy 'dir/*.py' (single argument with wildcard) expands correctly."""
        (tmp_path / "a.py").write_text("x: int = 1")
        (tmp_path / "b.py").write_text("y: str = 'hi'")
        (tmp_path / "c.txt").write_text("not python")

        from stubpy.cli import main
        rc = main([str(tmp_path / "*.py")])
        assert rc == 0
        assert (tmp_path / "a.pyi").exists()
        assert (tmp_path / "b.pyi").exists()
        assert not (tmp_path / "c.pyi").exists()

    def test_recursive_glob(self, tmp_path):
        """stubpy 'dir/**/*.py' matches nested directories."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.py").write_text("T: int = 1")
        (sub / "nested.py").write_text("N: str = 'n'")

        from stubpy.cli import main
        rc = main([str(tmp_path / "**" / "*.py")])
        assert rc == 0
        assert (tmp_path / "top.pyi").exists()
        assert (sub / "nested.pyi").exists()

    def test_no_match_is_a_usage_error(self, tmp_path, capsys):
        """A glob that matches nothing exits 2 with a message, does not crash."""
        from stubpy.cli import main
        rc = main([str(tmp_path / "*.py")])
        captured = capsys.readouterr()
        assert rc == 2
        assert "no python files" in captured.err.lower()

    def test_explicit_paths_still_work(self, tmp_path):
        """Non-glob explicit paths are unaffected by the expansion logic."""
        f = tmp_path / "mod.py"
        f.write_text("Z: int = 99")
        from stubpy.cli import main
        rc = main([str(f)])
        assert rc == 0
        assert (tmp_path / "mod.pyi").exists()

    def test_mixed_glob_and_explicit(self, tmp_path):
        """Mix of glob pattern and explicit path works correctly."""
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "util.py").write_text("A: int = 1")
        solo = tmp_path / "solo.py"
        solo.write_text("B: str = 'b'")

        from stubpy.cli import main
        rc = main([str(tmp_path / "*.py"), str(sub)])
        assert rc == 0
        assert (tmp_path / "solo.pyi").exists()
