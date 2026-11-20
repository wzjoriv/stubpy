"""Edge cases: module-level constructs."""
from __future__ import annotations

import ast

import stubpy
from stubpy.config import Config
from stubpy.core.pipeline import render_module
from stubpy.state.context import StubContext
from stubpy.state.diagnostics import Level
from tests.conftest import make_stub_ctx, write_tree


def _top_names(stub: str) -> list[str]:
    names: list[str] = []
    for node in ast.parse(stub).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


class TestModuleLevel:
    def test_dynamic_all_keeps_only_existing_names(self):
        stub, _ = make_stub_ctx("""
            __all__ = ["a", "missing"] + ["b"]
            __all__ += ["c"]
            def a() -> None: ...
            def b() -> None: ...
            def c() -> None: ...
            def d() -> None: ...
        """)
        assert _top_names(stub) == ["a", "b", "c"]

    _FALLBACKS = """
        try:
            from _stubpy_no_such_fast_module import f
        except ImportError:
            def f(x: int) -> int: ...
        import sys
        if sys.version_info >= (3, 8):
            def g(a: int) -> int: ...
        else:
            def g(a: int, b: int) -> int: ...
    """

    def test_try_import_with_fallback_def_gives_one_definition(self):
        stub, _ = make_stub_ctx(self._FALLBACKS)
        assert _top_names(stub).count("f") == 1
        assert "_stubpy_no_such_fast_module" not in stub
        assert (
            "if sys.version_info >= (3, 8):\n"
            "    def g(a: int) -> int: ...\n"
            "else:\n"
            "    def g(a: int, b: int) -> int: ...\n"
        ) in stub

    def test_resolved_version_branch_gives_one_definition(self):
        stub, _ = make_stub_ctx(self._FALLBACKS, version_branches="resolve")
        assert _top_names(stub).count("f") == 1
        assert _top_names(stub).count("g") == 1
        assert "def g(a: int) -> int: ..." in stub
        assert "_stubpy_no_such_fast_module" not in stub

    def test_module_getattr_is_emitted(self):
        stub, _ = make_stub_ctx("""
            def __getattr__(name: str) -> int:
                raise AttributeError(name)
        """)
        assert "def __getattr__(name: str) -> int" in stub

    def test_main_block_excluded_and_deleted_helper_absent(self):
        stub, _ = make_stub_ctx("""
            def helper() -> int: ...
            VALUE = helper()
            del helper
            def keep() -> None: ...
            if __name__ == "__main__":
                def main_only() -> None: ...
                SCRIPT_FLAG = True
        """)
        names = _top_names(stub)
        assert "keep" in names
        assert "helper" not in names and "main_only" not in names and "SCRIPT_FLAG" not in names

    def test_version_from_metadata_is_str(self):
        stub, _ = make_stub_ctx("""
            import importlib.metadata
            try:
                __version__ = importlib.metadata.version("stubpy-edge-no-such-dist")
            except importlib.metadata.PackageNotFoundError:
                __version__ = "0.0.0"
            __author__ = importlib.metadata.metadata.__name__
        """)
        assert "__version__: str" in stub
        assert "__author__: str" in stub
        assert stub.count("__version__") == 1

    def test_utf8_non_ascii_names(self):
        stub, _ = make_stub_ctx("""
            def café(naïve: str = "ü") -> str: ...
            class Größe:
                maß: int
        """)
        assert "def café(naïve: str = 'ü') -> str" in stub
        assert "class Größe" in stub


def test_star_import_of_module_with_all_becomes_explicit_reexports(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_star/__init__.py": "from .impl import *\n",
        "edgepkg_star/impl.py": "__all__ = ['f']\ndef f() -> int: ...\ndef _g() -> None: ...\n",
    })
    out = tmp_path / "out"
    result = stubpy.generate(pkg, out, config=Config())
    assert not result.failed
    init = (out / "edgepkg_star" / "__init__.pyi").read_text(encoding="utf-8")
    ast.parse(init)
    assert "from .impl import f as f" in init
    assert "import *" not in init and "_g" not in init


def test_lowercase_alias_of_a_class_is_kept(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_cls/__init__.py": "",
        "edgepkg_cls/el.py": "class Circle: ...\nclass Text: ...\nclass A: ...\n",
        "edgepkg_cls/al.py": (
            "from .el import A, Circle, Text\n__all__ = ['a', 'circle', 'text', 'limit', 'LIMIT_MAX']\n"
            "a = A\ncircle = Circle\ntext = Text\nLIMIT_MAX = 3\nlimit = LIMIT_MAX\n"
        ),
    })
    out = tmp_path / "out"
    assert not stubpy.generate(pkg, out, config=Config()).failed
    stub = (out / "edgepkg_cls" / "al.pyi").read_text(encoding="utf-8")
    ast.parse(stub)
    for line in ("a: TypeAlias = A", "circle: TypeAlias = Circle", "text: TypeAlias = Text"):
        assert line in stub
    assert "from .el import A, Circle, Text" in stub
    assert "TypeAlias = LIMIT_MAX" not in stub


def test_explicit_self_alias_is_reexported_even_when_missing_from_all(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_alias/__init__.py": (
            "from .impl import f, g as g, h as renamed\nfrom .impl import _p as _p\n__all__ = ['f']\n"
        ),
        "edgepkg_alias/impl.py": "\n".join(f"def {n}() -> int: ..." for n in ("f", "g", "h", "_p")),
    })
    out = tmp_path / "out"
    assert not stubpy.generate(pkg, out, config=Config()).failed
    init = (out / "edgepkg_alias" / "__init__.pyi").read_text(encoding="utf-8")
    assert "f as f" in init and "g as g" in init
    assert "renamed" not in init and "_p" not in init


def test_star_import_of_module_without_all_is_kept(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_star2/__init__.py": "from .impl import *\n",
        "edgepkg_star2/impl.py": "def f() -> int: ...\n",
    })
    out = tmp_path / "out"
    result = stubpy.generate(pkg, out, config=Config())
    assert not result.failed
    assert "from .impl import *" in (out / "edgepkg_star2" / "__init__.pyi").read_text(encoding="utf-8")


def test_spliced_all_is_resolved_and_written_to_the_stub(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_splice/__init__.py": (
            "from .impl import *\nfrom .impl import __all__ as _impl_all\n"
            "def g() -> None: ...\n__all__ = ['g', *_impl_all]\n"
        ),
        "edgepkg_splice/impl.py": "__all__ = ['f', 'h']\ndef f() -> int: ...\ndef h() -> int: ...\n",
    })
    out = tmp_path / "out"
    result = stubpy.generate(pkg, out, config=Config())
    assert not result.failed
    init = (out / "edgepkg_splice" / "__init__.pyi").read_text(encoding="utf-8")
    assert "from .impl import f as f, h as h" in init
    assert '__all__ = ["g", "f", "h"]' in init
    assert "def g() -> None: ..." in init


def test_local_module_named_like_stdlib_in_a_package(tmp_path):
    pkg = write_tree(tmp_path / "proj", {
        "edgepkg_shadow/__init__.py": "from .types import Local\n",
        "edgepkg_shadow/types.py": "class Local:\n    def ping(self) -> int: ...\n",
        "edgepkg_shadow/email.py": "import email.utils\ndef local_email() -> str: ...\n",
    })
    out = tmp_path / "out"
    result = stubpy.generate(pkg, out, config=Config())
    assert not result.failed, result.failed
    assert "class Local" in (out / "edgepkg_shadow" / "types.pyi").read_text(encoding="utf-8")
    assert "def local_email" in (out / "edgepkg_shadow" / "email.pyi").read_text(encoding="utf-8")


def test_loose_script_named_like_stdlib_module(tmp_path):
    src = write_tree(tmp_path, {"email.py": "def local_email() -> str: ...\n"}) / "email.py"
    stub = stubpy.render(str(src)).text
    assert "def local_email" in stub


def test_package_shadowing_an_already_imported_module(tmp_path):
    import json  # noqa: F401
    pkg = write_tree(tmp_path / "proj", {"json/__init__.py": "def local_json() -> int: ...\n"})
    ctx = StubContext()
    stub = render_module(str(pkg / "json" / "__init__.py"), ctx)
    assert "def local_json" in stub
    assert any(d.level == Level.WARNING and "json" in d.message for d in ctx.diagnostics)
