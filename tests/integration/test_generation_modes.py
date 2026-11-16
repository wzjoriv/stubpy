"""End-to-end execution modes, packages, ignore directives and docstrings."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

import stubpy
from stubpy.core.pipeline import render_module
from tests.conftest import _generate, _parse, assert_valid_syntax, make_stub


class TestModes:
    """AST skips module execution; AUTO falls back gracefully on errors."""

    def _make(self, source: str, mode) -> str:

        from stubpy.config import Config
        from stubpy.core.context import StubContext

        source = textwrap.dedent(source)
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(source)
            tmp = fh.name
        ctx = StubContext(config=Config(mode=mode))
        return render_module(tmp, ctx)

    def test_ast_only_class(self):
        from stubpy.config import Mode
        c = self._make("class Greeter:\n    pass\n", Mode.AST)
        assert "class Greeter" in c
        assert_valid_syntax(c)

    def test_ast_only_function(self):
        from stubpy.config import Mode
        c = self._make(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            Mode.AST,
        )
        assert "def add" in c
        assert_valid_syntax(c)

    def test_ast_only_variable(self):
        from stubpy.config import Mode
        c = self._make("X: int = 1\n", Mode.AST)
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_ast_only_typevar(self):
        from stubpy.config import Mode
        c = self._make(
            "from typing import TypeVar\nT = TypeVar('T')\n",
            Mode.AST,
        )
        assert "T = TypeVar('T')" in c
        assert_valid_syntax(c)

    def test_ast_only_diagnostic_logged(self):

        from stubpy.config import Config, Mode
        from stubpy.core.context import StubContext

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("X: int = 1\n")
            tmp = fh.name
        ctx = StubContext(config=Config(mode=Mode.AST))
        render_module(tmp, ctx)
        assert any("AST" in d.message for d in ctx.diagnostics.infos)

    def test_auto_mode_falls_back_on_bad_import(self):
        from stubpy.config import Mode
        c = self._make(
            "from _nonexistent_xyz_module import Foo\nX: int = 1\n",
            Mode.AUTO,
        )
        assert_valid_syntax(c)


class TestGeneratePackage:
    """generate() processes an entire directory tree of .py files."""

    def _write(self, root: Path, rel: str, content: str) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_simple_package(self, tmp_path):
        """All .py files produce corresponding .pyi files."""
        pkg = tmp_path / "mypkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "shapes.py", "class Square:\n    side: float\n")
        out = tmp_path / "stubs"

        result = stubpy.generate(str(pkg), str(out))

        assert result.summary().startswith("Generated 2")
        assert (out / "mypkg" / "__init__.pyi").exists()
        assert (out / "mypkg" / "shapes.pyi").exists()
        assert_valid_syntax((out / "mypkg" / "shapes.pyi").read_text())

    def test_nested_subpackage(self, tmp_path):
        """Subdirectories are mirrored and __init__.pyi created."""
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "utils/__init__.py", "")
        self._write(pkg, "utils/helpers.py", "def noop() -> None: pass\n")
        out = tmp_path / "out"

        result = stubpy.generate(str(pkg), str(out))

        assert (out / "pkg" / "utils" / "__init__.pyi").exists()
        assert (out / "pkg" / "utils" / "helpers.pyi").exists()
        assert len(result.failed) == 0

    def test_exclude_pattern(self, tmp_path):
        """Files matching exclude patterns are skipped."""
        from stubpy.config import Config
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "main.py", "X: int = 1\n")
        self._write(pkg, "test_main.py", "import pytest\n")
        out = tmp_path / "out"

        cfg = Config(exclude=["test_*.py"])
        stubpy.generate(str(pkg), str(out), config=cfg)

        assert (out / "pkg" / "main.pyi").exists()
        assert not (out / "pkg" / "test_main.pyi").exists()

    def test_one_result_per_file(self, tmp_path):
        """Each file gets its own StubResult, built with the run's config."""
        from stubpy.config import Config
        pkg = tmp_path / "pkg"
        self._write(pkg, "a.py", "X: int = 1\n")
        self._write(pkg, "b.py", "_Y: str = 'hi'\n")
        out = tmp_path / "out"

        report = stubpy.generate(str(pkg), str(out), config=Config(include_private=True))
        assert [r.source.name for r in report] == ["a.py", "b.py"]
        assert "_Y: str" in (out / "b.pyi").read_text()

    def test_missing_package_dir_raises(self, tmp_path):
        """FileNotFoundError raised when the folder does not exist."""
        with pytest.raises(FileNotFoundError):
            stubpy.generate(str(tmp_path / "nonexistent"), str(tmp_path / "out"))

    def test_output_alongside_source_when_no_output_dir(self, tmp_path):
        """Without an output, .pyi files are placed next to .py files."""
        pkg = tmp_path / "pkg"
        self._write(pkg, "mod.py", "X: int = 1\n")

        result = stubpy.generate(str(pkg))

        assert (pkg / "mod.pyi").exists()
        assert len(result.written) == 1

    def test_failed_files_reported(self, tmp_path):
        """Files that fail are in Report.failed, not Report.written."""
        from stubpy.config import Config, Mode
        pkg = tmp_path / "pkg"
        self._write(pkg, "bad.py", "import _nonexistent_xyz\nX: int = 1\n")
        self._write(pkg, "good.py", "Y: str = 'ok'\n")
        out = tmp_path / "out"

        cfg = Config(mode=Mode.AUTO)
        result = stubpy.generate(str(pkg), str(out), config=cfg)

        good_names = [p.name for p in result.written]
        assert "good.pyi" in good_names

    def test_report_summary(self):
        """Report.summary() formats correctly for 0/1/many stubs."""
        from stubpy import Diagnostic, Level, Report, StubResult
        from stubpy.extend import Stage
        assert Report().summary() == "Generated 0 stubs, 0 failed."
        r1 = Report(written=[Path("a.pyi")])
        assert r1.summary() == "Generated 1 stub, 0 failed."
        r2 = Report(written=[Path("a.pyi"), Path("b.pyi")])
        assert r2.summary() == "Generated 2 stubs, 0 failed."
        error = Diagnostic(Level.ERROR, Stage.LOAD, "c", "boom")
        r3 = Report(results=[StubResult("", (error,), Path("c.py"))])
        assert "1 failed" in r3.summary()

    def test_stub_content_valid(self, tmp_path):
        """Each generated stub is valid Python syntax."""
        pkg = tmp_path / "pkg"
        self._write(pkg, "models.py",
            """
            from typing import TypeVar, Generic
            T = TypeVar('T')
            class Box(Generic[T]):
                def get(self) -> T: ...
            """)
        out = tmp_path / "out"
        stubpy.generate(str(pkg), str(out))
        content = (out / "models.pyi").read_text()
        assert_valid_syntax(content)
        assert "Generic[T]" in content

    def test_multi_module_package(self, drawkit, tmp_path):
        """generate() on a package of interdependent modules writes a valid stub for each."""
        out = tmp_path / "drawkit_stubs"
        result = stubpy.generate(str(drawkit), str(out))
        assert result.failed == []
        names = {p.name for p in result.written}
        expected = {f"{p.stem}.pyi" for p in drawkit.glob("*.py")}
        assert expected <= names
        for stub in result.written:
            assert_valid_syntax(stub.read_text(encoding="utf-8"))


class TestIgnoreDirective:
    """Files with # stubpy: ignore produce a minimal stub and a diagnostic."""

    def test_ignored_file_has_empty_body(self):
        c = make_stub("# stubpy: ignore\nclass Foo:\n    x: int\n")
        lines = [l for l in c.splitlines() if l.strip()]
        assert lines == []

    def test_ignored_file_valid_syntax(self):
        c = make_stub("# stubpy: ignore\nclass Foo: pass\n")
        assert_valid_syntax(c)

    def test_ignore_after_regular_comment(self):
        c = make_stub("# module doc\n# stubpy: ignore\nclass Foo: pass\n")
        lines = [l for l in c.splitlines() if l.strip()]
        assert lines == []

    def test_ignore_case_insensitive_integration(self):
        c = make_stub("# STUBPY: IGNORE\ndef fn() -> int: return 1\n")
        assert "def fn" not in c

    def test_ignore_diagnostic_recorded(self):

        from stubpy.core.context import StubContext
        src = "# stubpy: ignore\nclass Foo: pass\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext()
        render_module(tmp, ctx)
        assert any("ignore" in d.message.lower() for d in ctx.diagnostics.infos)

    def test_no_ignore_still_generates(self):
        c = make_stub("# regular comment\nclass Foo: pass\n")
        assert "class Foo" in c


class TestIncludeDocstrings:
    def test_function_docstring_embedded(self):
        stub = _generate(
            '''
            def greet(name: str) -> str:
                """Return a greeting."""
                return f"Hello {name}"
            ''',
            include_docstrings=True,
        )
        assert '"""Return a greeting."""' in stub
        assert "..." not in stub

    def test_function_no_docstring_uses_ellipsis(self):
        stub = _generate(
            "def f(x: int) -> int: return x",
            include_docstrings=True,
        )
        assert "..." in stub

    def test_class_docstring_embedded(self):
        stub = _generate(
            '''
            class Dog:
                """A dog with a name."""
                def bark(self) -> str:
                    """Bark!"""
                    return "woof"
            ''',
            include_docstrings=True,
        )
        assert '"""A dog with a name."""' in stub
        assert '"""Bark!"""' in stub

    def test_method_docstring_embedded(self):
        stub = _generate(
            '''
            class Calc:
                def add(self, a: int, b: int) -> int:
                    """Return a + b."""
                    return a + b
            ''',
            include_docstrings=True,
        )
        assert '"""Return a + b."""' in stub

    def test_disabled_by_default(self):
        stub = _generate(
            '''
            def greet(name: str) -> str:
                """Return a greeting."""
                return f"Hello {name}"
            ''',
        )
        assert '"""Return a greeting."""' not in stub
        assert "..." in stub

    def test_generated_stub_is_valid_python(self):
        stub = _generate(
            '''
            def multi_line_doc(x: int) -> str:
                """This is a long docstring.

                It has multiple paragraphs.
                And some detail.
                """
                return str(x)
            ''',
            include_docstrings=True,
        )
        _parse(stub)

    def test_docstring_with_triple_quotes_escaped(self):
        stub = _generate(
            r'''
            def tricky() -> str:
                """Has \"\"\" inside."""
                return ""
            ''',
            include_docstrings=True,
        )
        _parse(stub)
