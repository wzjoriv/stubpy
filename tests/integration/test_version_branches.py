"""``sys.version_info`` / ``sys.platform`` branches copied into the stub (``version_branches = "emit"``)."""
import ast
import sys
import textwrap

import pytest

import stubpy
from stubpy.cli import main
from stubpy.config import Config, VersionBranches
from stubpy.core.diagnostics import Level
from tests.conftest import make_stub_ctx

MODULE = """
    import sys

    def compute():
        return 3

    if sys.version_info >= (3, 10):
        X = compute()

        class Thing:
            def go(self, n=compute()):
                return n

        if sys.platform == "win32":
            def helper() -> str: ...
        else:
            def helper() -> bytes: ...
    else:
        X = "old"

        class Thing:
            def go(self) -> None: ...

    if sys.version_info < (3, 0):
        from cStringIO import StringIO as Pretty
    else:
        from io import StringIO as Pretty

    __all__ = ["X", "Thing", "helper", "Pretty"]
"""


def _parses_on_310(text: str) -> None:
    ast.parse(text, feature_version=(3, 10))


class TestModuleLevel:
    def test_runtime_enriches_the_taken_branch(self):
        stub, _ = make_stub_ctx(MODULE)
        _parses_on_310(stub)
        assert stub == textwrap.dedent("""\
            import sys

            __all__ = ["X", "Thing", "helper", "Pretty"]

            if sys.version_info >= (3, 10):
                X: int

                class Thing:
                    def go(self, n: int = 3): ...

                if sys.platform == 'win32':
                    def helper() -> str: ...
                else:
                    def helper() -> bytes: ...
            else:
                X: str

                class Thing:
                    def go(self) -> None: ...

            if sys.version_info < (3, 0):
                from cStringIO import StringIO as Pretty
            else:
                from io import StringIO as Pretty
        """)

    def test_ast_mode_emits_every_branch_from_the_source(self):
        stub, _ = make_stub_ctx(MODULE, imports="none")
        _parses_on_310(stub)
        assert "if sys.version_info >= (3, 10):\n    class Thing:\n        def go(self, n=...): ..." in stub
        assert "else:\n    X: str\n\n    class Thing:\n        def go(self) -> None: ..." in stub
        assert "    if sys.platform == 'win32':\n        def helper() -> str: ...\n    else:\n" in stub

    def test_resolve_keeps_only_the_taken_branch(self):
        stub, _ = make_stub_ctx(MODULE, version_branches="resolve")
        assert "if sys" not in stub and "import sys" not in stub
        assert "def go(self, n" in stub and "def go(self) -> None" not in stub
        assert "from io import StringIO as Pretty" in stub and "cStringIO" not in stub
        assert ("def helper() -> str: ..." in stub) == (sys.platform == "win32")

    def test_branch_imports_stay_in_their_branch(self):
        stub, _ = make_stub_ctx("""
            import sys
            if sys.version_info >= (3, 11):
                from typing import Self
            else:
                from typing_extensions import Self

            class Box:
                def me(self) -> Self:
                    return self
        """)
        assert stub == textwrap.dedent("""\
            import sys

            if sys.version_info >= (3, 11):
                from typing import Self
            else:
                from typing_extensions import Self

            class Box:
                def me(self) -> Self: ...
        """)

    def test_unused_branch_imports_are_dropped(self):
        stub, _ = make_stub_ctx("""
            import sys
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import json as tomllib
            def f() -> int: ...
        """)
        assert stub == "def f() -> int: ...\n"

    def test_other_tests_keep_todays_behaviour(self):
        stub, _ = make_stub_ctx("""
            import os
            from typing import TYPE_CHECKING
            HAS_X = bool(os.environ.get("X"))
            if TYPE_CHECKING:
                def typed() -> int: ...
            if HAS_X:
                def a() -> int: ...
            else:
                def b() -> int: ...
            if os.environ.get("Y"):
                def c() -> int: ...
        """)
        assert "if " not in stub
        for name in ("typed", "a", "b", "c"):
            assert f"def {name}() -> int: ..." in stub

    def test_elif_chain_and_platform_startswith(self):
        stub, _ = make_stub_ctx("""
            import sys
            if sys.platform.startswith("linux"):
                LIMIT: int = 1
            elif sys.platform == "darwin" or sys.platform == "win32":
                LIMIT: float = 2.0
            elif not sys.version_info[:2] >= (3, 10):
                LIMIT: str = ""
        """)
        assert stub.endswith(textwrap.dedent("""\
            if sys.platform.startswith('linux'):
                LIMIT: int
            elif sys.platform == 'darwin' or sys.platform == 'win32':
                LIMIT: float
            elif not sys.version_info[:2] >= (3, 10):
                LIMIT: str
        """))

    def test_empty_leading_branch_gets_ellipsis(self):
        stub, _ = make_stub_ctx("""
            import sys
            if sys.version_info >= (3, 10):
                pass
            else:
                def legacy() -> None: ...
        """)
        assert stub.endswith("if sys.version_info >= (3, 10):\n    ...\nelse:\n    def legacy() -> None: ...\n")

    def test_all_lists_names_bound_in_branches(self):
        stub, _ = make_stub_ctx("""
            import sys
            __all__ = ["f", "missing"]
            if sys.version_info >= (3, 10):
                def f() -> int: ...
            else:
                def f() -> str: ...
        """)
        assert '__all__ = ["f"]' in stub


class TestClassLevel:
    SOURCE = """
        import sys

        def compute():
            return 3

        class Box:
            size: int

            def keep(self) -> None: ...

            if sys.version_info >= (3, 10):
                def new(self, x=compute()):
                    return x
            else:
                def old(self) -> None: ...
    """

    def test_runtime_takes_the_live_method_and_ast_for_the_rest(self):
        stub, _ = make_stub_ctx(self.SOURCE)
        assert textwrap.dedent("""\
            class Box:
                size: int

                def keep(self) -> None: ...

                if sys.version_info >= (3, 10):
                    def new(self, x: int = 3): ...
                else:
                    def old(self) -> None: ...
        """) in stub
        assert stub.startswith("import sys\n")

    def test_ast_mode(self):
        stub, _ = make_stub_ctx(self.SOURCE, imports="none")
        assert "    if sys.version_info >= (3, 10):\n        def new(self, x=...): ...\n    else:\n" in stub
        assert "        def old(self) -> None: ...\n" in stub

    def test_attributes_in_branches(self):
        stub, _ = make_stub_ctx("""
            import sys
            class Cfg:
                if sys.platform == "win32":
                    sep: str = "\\\\"
                else:
                    sep: bytes = b"/"
        """)
        assert stub.endswith(textwrap.dedent("""\
            class Cfg:
                if sys.platform == 'win32':
                    sep: str
                else:
                    sep: bytes
        """))


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax needs Python 3.12 to parse the source")
class TestPep695InBranches:
    SOURCE = """
        import sys
        if sys.version_info >= (3, 12):
            def first[T](xs: list[T]) -> T:
                return xs[0]

            type Pair[K] = tuple[K, K]

            class Stack[T: (int, str)]:
                def push(self, item: T) -> None: ...

            def call[**P, R](f: Callable[P, R]) -> Callable[P, R]: ...
        else:
            def first(xs: list) -> object:
                return xs[0]
    """

    def test_lowered_to_typevars_and_parses_on_310(self):
        stub, _ = make_stub_ctx("from collections.abc import Callable\n" + textwrap.dedent(self.SOURCE))
        _parses_on_310(stub)
        assert stub.split("\n\n", 1)[1] == textwrap.dedent('''\
            if sys.version_info >= (3, 12):
                T = TypeVar("T")

                def first(xs: list[T]) -> T: ...

                K = TypeVar("K")

                Pair: TypeAlias = tuple[K, K]

                T_1 = TypeVar("T_1", int, str)

                class Stack(Generic[T_1]):
                    def push(self, item: T_1) -> None: ...

                P = ParamSpec("P")
                R = TypeVar("R")

                def call(f: Callable[P, R]) -> Callable[P, R]: ...
            else:
                def first(xs: list) -> object: ...
        ''')

    def test_unconditional_pep695_is_kept(self):
        stub, _ = make_stub_ctx("def first[T](xs: list[T]) -> T:\n    return xs[0]\n", imports="none")
        assert "def first[T](xs: list[T]) -> T: ..." in stub


@pytest.mark.skipif(sys.version_info >= (3, 12), reason="checks a source this Python cannot parse")
def test_unparsable_branch_keeps_the_ast_diagnostic(tmp_path):
    src = tmp_path / "new_syntax.py"
    src.write_text("import sys\nif sys.version_info >= (3, 12):\n    type X = int\n", encoding="utf-8")
    result = stubpy.render(src, config=Config(imports="none"))
    errors = [d for d in result.diagnostics if d.level is Level.ERROR]
    assert errors and "does not parse" in errors[0].message


class TestOption:
    def test_default_is_emit(self):
        assert Config().version_branches is VersionBranches.EMIT

    def test_strings_and_toml_key(self, tmp_path):
        assert Config(version_branches="resolve").version_branches is VersionBranches.RESOLVE
        assert Config.from_dict({"version-branches": "resolve"}).version_branches is VersionBranches.RESOLVE
        with pytest.raises(ValueError, match="version_branches"):
            Config(version_branches="maybe")
        (tmp_path / "stubpy.toml").write_text('version_branches = "resolve"\n', encoding="utf-8")
        assert stubpy.load_config(tmp_path).version_branches is VersionBranches.RESOLVE

    def test_cli_flag(self, tmp_path, capsys):
        src = tmp_path / "cli_branches.py"
        src.write_text("import sys\nif sys.version_info >= (3, 0):\n    A: int = 1\nelse:\n    A: str = ''\n",
                       encoding="utf-8")
        assert main(["render", str(src), "--no-config"]) == 0
        assert "if sys.version_info >= (3, 0):" in capsys.readouterr().out
        assert main(["render", str(src), "--no-config", "--version-branches", "resolve"]) == 0
        out = capsys.readouterr().out
        assert "if sys" not in out and "A: int" in out
