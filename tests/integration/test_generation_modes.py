"""End-to-end execution modes, packages, ignore directives and docstrings."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from stubpy import generate_stub
from tests.conftest import _generate, _parse, assert_valid_syntax, make_stub


class TestExecutionModes:
    """AST_ONLY skips module execution; AUTO falls back gracefully on errors."""

    def _make(self, source: str, mode) -> str:

        from stubpy.config import StubConfig
        from stubpy.core.context import StubContext

        source = textwrap.dedent(source)
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(source)
            tmp = fh.name
        out = Path(tmp).with_suffix(".pyi").as_posix()
        ctx = StubContext(config=StubConfig(execution_mode=mode))
        return generate_stub(tmp, out, ctx=ctx)

    def test_ast_only_class(self):
        from stubpy.config import ExecutionMode
        c = self._make("class Greeter:\n    pass\n", ExecutionMode.AST_ONLY)
        assert "class Greeter" in c
        assert_valid_syntax(c)

    def test_ast_only_function(self):
        from stubpy.config import ExecutionMode
        c = self._make(
            "def add(a: int, b: int) -> int:\n    return a + b\n",
            ExecutionMode.AST_ONLY,
        )
        assert "def add" in c
        assert_valid_syntax(c)

    def test_ast_only_variable(self):
        from stubpy.config import ExecutionMode
        c = self._make("X: int = 1\n", ExecutionMode.AST_ONLY)
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_ast_only_typevar(self):
        from stubpy.config import ExecutionMode
        c = self._make(
            "from typing import TypeVar\nT = TypeVar('T')\n",
            ExecutionMode.AST_ONLY,
        )
        assert "T = TypeVar('T')" in c
        assert_valid_syntax(c)

    def test_ast_only_diagnostic_logged(self):

        from stubpy.config import ExecutionMode, StubConfig
        from stubpy.core.context import StubContext

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("X: int = 1\n")
            tmp = fh.name
        ctx = StubContext(config=StubConfig(execution_mode=ExecutionMode.AST_ONLY))
        generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        assert any("AST_ONLY" in d.message for d in ctx.diagnostics.infos)

    def test_auto_mode_falls_back_on_bad_import(self):
        from stubpy.config import ExecutionMode
        c = self._make(
            "from _nonexistent_xyz_module import Foo\nX: int = 1\n",
            ExecutionMode.AUTO,
        )
        assert_valid_syntax(c)


class TestGeneratePackage:
    """generate_package processes an entire directory tree of .py files."""

    def _write(self, root: Path, rel: str, content: str) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_simple_package(self, tmp_path):
        """All .py files produce corresponding .pyi files."""
        from stubpy import generate_package
        pkg = tmp_path / "mypkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "shapes.py", "class Square:\n    side: float\n")
        out = tmp_path / "stubs"

        result = generate_package(str(pkg), str(out))

        assert result.summary().startswith("Generated 2")
        assert (out / "__init__.pyi").exists()
        assert (out / "shapes.pyi").exists()
        assert_valid_syntax((out / "shapes.pyi").read_text())

    def test_nested_subpackage(self, tmp_path):
        """Subdirectories are mirrored and __init__.pyi created."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "utils/__init__.py", "")
        self._write(pkg, "utils/helpers.py", "def noop() -> None: pass\n")
        out = tmp_path / "out"

        result = generate_package(str(pkg), str(out))

        assert (out / "utils" / "__init__.pyi").exists()
        assert (out / "utils" / "helpers.pyi").exists()
        assert len(result.failed) == 0

    def test_exclude_pattern(self, tmp_path):
        """Files matching exclude patterns are skipped."""
        from stubpy import generate_package
        from stubpy.config import StubConfig
        pkg = tmp_path / "pkg"
        self._write(pkg, "__init__.py", "")
        self._write(pkg, "main.py", "X: int = 1\n")
        self._write(pkg, "test_main.py", "import pytest\n")
        out = tmp_path / "out"

        cfg = StubConfig(exclude=["test_*.py"])
        generate_package(str(pkg), str(out), config=cfg)

        assert (out / "main.pyi").exists()
        assert not (out / "test_main.pyi").exists()

    def test_ctx_factory_used(self, tmp_path):
        """ctx_factory is called once per file."""
        from stubpy import generate_package
        from stubpy.core.context import StubContext
        pkg = tmp_path / "pkg"
        self._write(pkg, "a.py", "X: int = 1\n")
        self._write(pkg, "b.py", "Y: str = 'hi'\n")
        out = tmp_path / "out"

        calls: list[StubContext] = []

        def factory() -> StubContext:
            ctx = StubContext()
            calls.append(ctx)
            return ctx

        generate_package(str(pkg), str(out), ctx_factory=factory)
        assert len(calls) == 2

    def test_missing_package_dir_raises(self, tmp_path):
        """FileNotFoundError raised when package_dir does not exist."""
        from stubpy import generate_package
        with pytest.raises(FileNotFoundError):
            generate_package(str(tmp_path / "nonexistent"), str(tmp_path / "out"))

    def test_output_alongside_source_when_no_output_dir(self, tmp_path):
        """When output_dir is None, .pyi files are placed next to .py files."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "mod.py", "X: int = 1\n")

        result = generate_package(str(pkg))

        assert (pkg / "mod.pyi").exists()
        assert len(result.stubs_written) == 1

    def test_failed_files_reported(self, tmp_path):
        """Files that fail are in PackageResult.failed, not stubs_written."""
        from stubpy import generate_package
        from stubpy.config import ExecutionMode, StubConfig
        pkg = tmp_path / "pkg"
        self._write(pkg, "bad.py", "import _nonexistent_xyz\nX: int = 1\n")
        self._write(pkg, "good.py", "Y: str = 'ok'\n")
        out = tmp_path / "out"

        cfg = StubConfig(execution_mode=ExecutionMode.AUTO)
        result = generate_package(str(pkg), str(out), config=cfg)

        good_names = [p.name for p in result.stubs_written]
        assert "good.pyi" in good_names

    def test_package_result_summary(self):
        """PackageResult.summary() formats correctly for 0/1/many stubs."""
        from stubpy.core.results import PackageResult
        assert PackageResult().summary() == "Generated 0 stubs, 0 failed."
        r1 = PackageResult(stubs_written=[Path("a.pyi")])
        assert r1.summary() == "Generated 1 stub, 0 failed."
        r2 = PackageResult(stubs_written=[Path("a.pyi"), Path("b.pyi")])
        assert r2.summary() == "Generated 2 stubs, 0 failed."
        r3 = PackageResult(failed=[(Path("c.py"), [])])
        assert "1 failed" in r3.summary()

    def test_stub_content_valid(self, tmp_path):
        """Each generated stub is valid Python syntax."""
        from stubpy import generate_package
        pkg = tmp_path / "pkg"
        self._write(pkg, "models.py",
            """
            from typing import TypeVar, Generic
            T = TypeVar('T')
            class Box(Generic[T]):
                def get(self) -> T: ...
            """)
        out = tmp_path / "out"
        generate_package(str(pkg), str(out))
        content = (out / "models.pyi").read_text()
        assert_valid_syntax(content)
        assert "Generic[T]" in content

    def test_demo_package(self, demo_dir, tmp_path):
        """generate_package on the demo/ package produces all stubs."""
        from stubpy import generate_package
        out = tmp_path / "demo_stubs"
        result = generate_package(str(demo_dir), str(out))
        assert len(result.stubs_written) > 0
        for stub in result.stubs_written:
            assert_valid_syntax(stub.read_text())


class TestIgnoreDirective:
    """Files with # stubpy: ignore produce a minimal stub and a diagnostic."""

    def test_ignored_file_has_empty_body(self):
        c = make_stub("# stubpy: ignore\nclass Foo:\n    x: int\n")
        lines = [l for l in c.splitlines() if l.strip() and not l.startswith("from __future__")]
        assert lines == []

    def test_ignored_file_valid_syntax(self):
        c = make_stub("# stubpy: ignore\nclass Foo: pass\n")
        assert_valid_syntax(c)

    def test_ignore_after_regular_comment(self):
        c = make_stub("# module doc\n# stubpy: ignore\nclass Foo: pass\n")
        lines = [l for l in c.splitlines() if l.strip() and not l.startswith("from __future__")]
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
        generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
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
