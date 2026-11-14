"""Edge cases: module-level constructs."""
from __future__ import annotations

import ast

import pytest

from stubpy import generate_package, generate_stub
from stubpy.config import ExecutionMode, StubConfig
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import DiagnosticLevel
from tests.conftest import make_stub_ctx, write_tree

MODES = ["runtime", "ast_only"]


def _top_names(stub: str) -> list[str]:
    names: list[str] = []
    for node in ast.parse(stub).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


@pytest.mark.parametrize("mode", MODES)
class TestModuleLevel:
    def test_dynamic_all_keeps_only_existing_names(self, mode):
        stub, _ = make_stub_ctx("""
            __all__ = ["a", "missing"] + ["b"]
            __all__ += ["c"]
            def a() -> None: ...
            def b() -> None: ...
            def c() -> None: ...
            def d() -> None: ...
        """, mode)
        assert _top_names(stub) == ["a", "b", "c"]

    def test_try_import_with_fallback_def_gives_one_definition(self, mode):
        stub, _ = make_stub_ctx("""
            try:
                from _stubpy_no_such_fast_module import f
            except ImportError:
                def f(x: int) -> int: ...
            import sys
            if sys.version_info >= (3, 8):
                def g(a: int) -> int: ...
            else:
                def g(a: int, b: int) -> int: ...
        """, mode)
        assert _top_names(stub).count("f") == 1
        assert _top_names(stub).count("g") == 1
        assert "_stubpy_no_such_fast_module" not in stub

    def test_module_getattr_is_emitted(self, mode):
        stub, _ = make_stub_ctx("""
            def __getattr__(name: str) -> int:
                raise AttributeError(name)
        """, mode)
        assert "def __getattr__(name: str) -> int" in stub

    def test_main_block_excluded_and_deleted_helper_absent(self, mode):
        stub, _ = make_stub_ctx("""
            def helper() -> int: ...
            VALUE = helper()
            del helper
            def keep() -> None: ...
            if __name__ == "__main__":
                def main_only() -> None: ...
                SCRIPT_FLAG = True
        """, mode)
        names = _top_names(stub)
        assert "keep" in names
        assert "helper" not in names and "main_only" not in names and "SCRIPT_FLAG" not in names

    def test_version_from_metadata_is_str(self, mode):
        stub, _ = make_stub_ctx("""
            import importlib.metadata
            try:
                __version__ = importlib.metadata.version("stubpy-edge-no-such-dist")
            except importlib.metadata.PackageNotFoundError:
                __version__ = "0.0.0"
            __author__ = importlib.metadata.metadata.__name__
        """, mode)
        assert "__version__: str" in stub
        assert "__author__: str" in stub
        assert stub.count("__version__") == 1

    def test_utf8_non_ascii_names(self, mode):
        stub, _ = make_stub_ctx("""
            def café(naïve: str = "ü") -> str: ...
            class Größe:
                maß: int
        """, mode)
        assert "def café(naïve: str = 'ü') -> str" in stub
        assert "class Größe" in stub


@pytest.mark.parametrize("mode", MODES)
def test_star_import_is_kept_as_reexport(tmp_path, mode):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_star/__init__.py": "from .impl import *\n",
        "edgepkg_star/impl.py": "__all__ = ['f']\ndef f() -> int: ...\ndef _g() -> None: ...\n",
    })
    out = tmp_path / "out"
    result = generate_package(pkg, out, config=StubConfig(execution_mode=ExecutionMode(mode)))
    assert not result.failed
    init = (out / "edgepkg_star" / "__init__.pyi").read_text(encoding="utf-8")
    ast.parse(init)
    assert "from .impl import *" in init


@pytest.mark.parametrize("mode", MODES)
def test_local_module_named_like_stdlib_in_a_package(tmp_path, mode):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_shadow/__init__.py": "from .types import Local\n",
        "edgepkg_shadow/types.py": "class Local:\n    def ping(self) -> int: ...\n",
        "edgepkg_shadow/email.py": "import email.utils\ndef local_email() -> str: ...\n",
    })
    out = tmp_path / "out"
    result = generate_package(pkg, out, config=StubConfig(execution_mode=ExecutionMode(mode)))
    assert not result.failed, result.failed
    assert "class Local" in (out / "edgepkg_shadow" / "types.pyi").read_text(encoding="utf-8")
    assert "def local_email" in (out / "edgepkg_shadow" / "email.pyi").read_text(encoding="utf-8")


def test_loose_script_named_like_stdlib_module(tmp_path):
    src = write_tree(tmp_path, {"email.py": "def local_email() -> str: ...\n"}) / "email.py"
    stub = generate_stub(str(src), str(tmp_path / "email.pyi"))
    assert "def local_email" in stub


def test_package_shadowing_an_already_imported_module(tmp_path):
    import json  # noqa: F401
    pkg = write_tree(tmp_path / "proj", {"json/__init__.py": "def local_json() -> int: ...\n"})
    ctx = StubContext()
    stub = generate_stub(str(pkg / "json" / "__init__.py"), str(tmp_path / "out.pyi"), ctx=ctx)
    assert "def local_json" in stub
    assert any(d.level == DiagnosticLevel.WARNING and "json" in d.message for d in ctx.diagnostics)
