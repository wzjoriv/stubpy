"""Edge cases: importing real modules and packages for runtime introspection."""
from __future__ import annotations

import ast
import sys

import pytest

import stubpy
from stubpy.analysis.syntax import NewerSyntaxError
from stubpy.config import Config
from stubpy.core.pipeline import render_module
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Level, Stage
from tests.conftest import write_tree

DEFAULT = Config()


def _stubs(out) -> dict[str, str]:
    return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in out.rglob("*.pyi")}


class TestRelativeImports:
    def test_package_with_relative_imports_loads_at_runtime(self, tmp_path):
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_rel/__init__.py": "from .core import Base\n__all__ = ['Base']\n",
            "edgepkg_rel/core.py": "class Base:\n    def __init__(self, size: int = 1) -> None: ...\n",
            "edgepkg_rel/sub/__init__.py": "",
            "edgepkg_rel/sub/child.py": """
                from ..core import Base
                class Child(Base):
                    def __init__(self, label: str, **kwargs) -> None:
                        super().__init__(**kwargs)
            """,
        })
        out = tmp_path / "out"
        result = stubpy.generate(pkg / "edgepkg_rel", out, config=DEFAULT)
        assert not result.failed, result.failed
        child = _stubs(out)["edgepkg_rel/sub/child.pyi"]
        assert "size: int = 1" in child
        assert "edgepkg_rel" not in sys.modules

    def test_single_file_inside_package_loads_by_dotted_name(self, tmp_path):
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_one/__init__.py": "",
            "edgepkg_one/a.py": "VALUE: int = 1\n",
            "edgepkg_one/b.py": "from .a import VALUE\ndef get() -> int: ...\n",
        })
        ctx = StubContext(config=DEFAULT)
        stub = render_module(str(pkg / "edgepkg_one" / "b.py"), ctx)
        assert "def get() -> int" in stub
        assert not ctx.diagnostics.has_errors()
        assert ctx.module_name == "edgepkg_one.b"


class TestImportTimeFailures:
    @pytest.mark.parametrize("body, kind", [
        ("import sys\nsys.exit(3)\n", "SystemExit"),
        ("import argparse\nparser = argparse.ArgumentParser()\nparser.add_argument('src')\n"
         "parser.add_argument('dest')\nparser.parse_args()\n", "SystemExit"),
        ("import os\nTOKEN = os.environ['STUBPY_EDGE_SURELY_MISSING_VAR']\n", "KeyError"),
    ])
    def test_failed_import_falls_back_to_the_source(self, tmp_path, body, kind):
        src = write_tree(tmp_path, {"script.py": body + "def api(x: int) -> int: ...\n"}) / "script.py"
        ctx = StubContext(config=DEFAULT)
        stub = render_module(str(src), ctx)
        assert "def api(x: int) -> int" in stub
        warnings = [d for d in ctx.diagnostics if d.level == Level.WARNING and d.stage == Stage.LOAD]
        assert warnings and kind in warnings[0].message

    def test_argv_is_set_during_import_and_restored(self, tmp_path):
        src = write_tree(tmp_path, {"argv_probe.py": "import sys\nSEEN = list(sys.argv)\n"}) / "argv_probe.py"
        before = list(sys.argv)
        stubpy.render(str(src))
        assert sys.argv == before

    def test_package_run_with_failing_imports_has_no_failures(self, tmp_path):
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_auto/__init__.py": "",
            "edgepkg_auto/bad.py": "raise RuntimeError('boom')\ndef api() -> int: ...\n",
        })
        out = tmp_path / "out"
        result = stubpy.generate(pkg / "edgepkg_auto", out, config=DEFAULT)
        assert not result.failed
        assert "def api() -> int" in _stubs(out)["edgepkg_auto/bad.pyi"]


class TestLayouts:
    def test_namespace_package_below_explicit_root(self, tmp_path):
        root = write_tree(tmp_path / "proj", {
            "edgens/sub/__init__.py": "",
            "edgens/sub/helpers.py": "def helper(n: int = 2) -> int: ...\n",
            "edgens/sub/api.py": """
                from edgens.sub.helpers import helper
                def run(**kwargs) -> int:
                    return helper(**kwargs)
            """,
        })
        out = tmp_path / "out"
        result = stubpy.generate(root, out, config=DEFAULT)
        assert not result.failed, result.failed
        assert "n: int = 2" in _stubs(out)["edgens/sub/api.pyi"]

    def test_src_layout(self, tmp_path):
        project = write_tree(tmp_path / "project", {
            "pyproject.toml": "[project]\nname = 'edgesrc'\n",
            "src/edgesrc_pkg/__init__.py": "from .mod import thing\n",
            "src/edgesrc_pkg/mod.py": "from . import _impl\ndef thing(x: int) -> int: ...\n",
            "src/edgesrc_pkg/_impl.py": "",
        })
        out = tmp_path / "out"
        result = stubpy.generate(project, out, config=DEFAULT)
        assert not result.failed, result.failed
        assert "def thing(x: int) -> int" in _stubs(out)["src/edgesrc_pkg/mod.pyi"]

    def test_module_replacing_itself_in_sys_modules(self, tmp_path):
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_repl/__init__.py": "",
            "edgepkg_repl/magic.py": """
                import sys
                class _Proxy:
                    value = 1
                def api(x: int) -> int: ...
                sys.modules[__name__] = _Proxy()
            """,
        })
        out = tmp_path / "out"
        result = stubpy.generate(pkg / "edgepkg_repl", out, config=DEFAULT)
        assert not result.failed
        stub = _stubs(out)["edgepkg_repl/magic.pyi"]
        ast.parse(stub)
        assert "def api(x: int) -> int" in stub

    def test_package_modules_imported_once_per_run(self, tmp_path):
        log = tmp_path / "imports.log"
        body = f"with open({str(log)!r}, 'a') as _log:\n    _log.write(__name__ + '\\n')\n"
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_once/__init__.py": body + "from . import a, b\n",
            "edgepkg_once/a.py": body + "from .b import B\n",
            "edgepkg_once/b.py": body + "class B: ...\n",
        })
        stubpy.generate(pkg / "edgepkg_once", tmp_path / "out", config=DEFAULT)
        lines = log.read_text().splitlines()
        assert sorted(lines) == ["edgepkg_once", "edgepkg_once.a", "edgepkg_once.b"]

    def test_sys_path_and_modules_restored(self, tmp_path):
        import json  # noqa: F401
        pkg = write_tree(tmp_path / "proj", {
            "edgepkg_clean/__init__.py": "import json\nfrom . import inner\n",
            "edgepkg_clean/inner.py": "X: int = 1\n",
        })
        path_before = list(sys.path)
        stubpy.generate(pkg / "edgepkg_clean", tmp_path / "out", config=DEFAULT)
        assert sys.path == path_before
        assert "edgepkg_clean" not in sys.modules and "edgepkg_clean.inner" not in sys.modules
        assert "json" in sys.modules


class TestPep695:
    SOURCE = "type Vector = list[float]\ntype Pair[N: (int, float)] = tuple[N, N]\n"

    @pytest.mark.skipif(sys.version_info >= (3, 12), reason="checks the diagnostic on Python < 3.12")
    def test_clean_diagnostic_before_312(self, tmp_path):
        src = write_tree(tmp_path, {"aliases.py": self.SOURCE}) / "aliases.py"
        with pytest.raises(NewerSyntaxError, match="needs Python 3.12"):
            render_module(str(src), StubContext(config=Config()))
        result = stubpy.render(src)
        assert result.ok and not result.text and "needs Python 3.12" in result.warnings[0].message

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax needs Python 3.12")
    def test_aliases_stubbed_on_312(self, tmp_path):
        src = write_tree(tmp_path, {"aliases.py": self.SOURCE}) / "aliases.py"
        ctx = StubContext()
        stub = render_module(str(src), ctx)
        assert "Vector" in stub and not ctx.diagnostics.has_errors()
