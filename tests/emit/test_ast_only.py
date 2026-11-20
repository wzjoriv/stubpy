"""Tests for AST-only stub quality."""
from __future__ import annotations

from stubpy.core.pipeline import render_module


class TestASTOnlyModeQuality:
    """AST-only mode produces rich stubs with type inference from defaults."""

    def _ast_stub(self, src: str) -> str:
        import tempfile
        import textwrap
        from pathlib import Path

        from stubpy.config import Config
        from stubpy.state.context import StubContext
        src = textwrap.dedent(src)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = Path(f.name)
        try:
            ctx = StubContext(config=Config(imports="none"))
            return render_module(str(tmp), ctx)
        finally:
            tmp.unlink(missing_ok=True)
            tmp.with_suffix(".pyi").unlink(missing_ok=True)

    def test_module_variable_type_from_literal(self):
        stub = self._ast_stub("MAX = 100\nLABEL = 'hi'\nFLAG = True\n")
        assert "MAX: int" in stub
        assert "LABEL: str" in stub
        assert "FLAG: bool" in stub

    def test_function_params_present_in_ast_only(self):
        stub = self._ast_stub("def f(x=0, y='hi', z=True): ...\n")
        assert "def f(" in stub
        assert "x: int = 0" in stub
        assert "z: bool = True" in stub

    def test_inferred_types_for_unannotated_params_from_defaults(self):
        """Literal defaults produce real type annotations, not # type: comments."""
        stub = self._ast_stub("def f(x=0, y='hi', active=True): ...\n")
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub
        assert "# type:" not in stub

    def test_explicit_annotations_respected(self):
        stub = self._ast_stub("def f(x: int, y: str = 'hi'): ...\n")
        assert "x: int" in stub
        assert "y: str = 'hi'" in stub
        fn_part = stub.split("def f(")[1]
        assert "# type:" not in fn_part

    def test_return_annotation_preserved(self):
        stub = self._ast_stub("def f() -> bool: ...\n")
        assert "-> bool" in stub

    def test_class_method_params_in_ast_only(self):
        stub = self._ast_stub(
            "class Widget:\n"
            "    def __init__(self, x=0, y='text', active=True):\n"
            "        pass\n"
        )
        assert "def __init__" in stub
        assert "x: int = 0" in stub
        assert "active: bool = True" in stub

    def test_ast_only_stub_is_valid_syntax(self):
        from tests.conftest import assert_valid_syntax
        stub = self._ast_stub(
            "X = 100\nY = 'hi'\n\n"
            "def f(a=1, b='x', c=True, *args, d=3.14, **kw): ...\n\n"
            "class C:\n"
            "    def m(self, x=0, y='text'): pass\n"
        )
        assert_valid_syntax(stub)

    def test_positional_only_and_kw_only_in_ast_only(self):
        stub = self._ast_stub(
            "def f(x: int, y=1.0, /, z: str = 'hi', *, debug=False): ...\n"
        )
        assert "x: int" in stub
        assert "y: float" in stub
        assert "z: str = 'hi'" in stub
        assert "debug: bool" in stub
