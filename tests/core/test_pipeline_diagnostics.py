"""Diagnostics recorded by the render pipeline."""
from __future__ import annotations

from stubpy.core.pipeline import render_module
from stubpy.state.diagnostics import Level


class TestDiagnosticsFromGeneration:
    """Integration tests for diagnostics emitted by the full render pipeline."""

    def _ctx(self, **cfg_kwargs):
        from stubpy.config import Config
        from stubpy.state.context import StubContext
        return StubContext(config=Config(verbose=True, **cfg_kwargs))

    def _generate(self, tmp_path, src, **cfg_kwargs):
        import textwrap

        src_p = tmp_path / "mod.py"
        src_p.write_text(textwrap.dedent(src))
        ctx = self._ctx(**cfg_kwargs)
        stub = render_module(str(src_p), ctx)
        return stub, ctx.diagnostics

    def test_diagnostic_level_ordering(self):
        assert Level.INFO    < Level.WARNING < Level.ERROR
        assert Level.INFO    <= Level.INFO
        assert Level.WARNING >= Level.WARNING
        assert Level.ERROR   >= Level.WARNING
        assert not (Level.INFO >= Level.WARNING)

    def test_filter_by_level_gte(self, tmp_path):
        stub, diags = self._generate(tmp_path, "X: int = 1\n")
        warns_and_above = [d for d in diags.all if d.level >= Level.WARNING]
        assert isinstance(warns_and_above, list)

    def test_non_literal_default_no_annotation_leak(self, tmp_path):
        """AST-only: x=os.sep must not produce x: _NonLiteralDefault."""
        stub, diags = self._generate(
            tmp_path, "def f(x=os.sep): pass\n",
            imports="none",
        )
        assert "_NonLiteralDefault" not in stub
        assert "x=..." in stub

    def test_complex_default_no_annotation_leak(self, tmp_path):
        """AST-only: x=SomeClass() must not produce x: _NonLiteralDefault."""
        stub, diags = self._generate(
            tmp_path, "def f(x=list(), y=dict()): pass\n",
            imports="none",
        )
        assert "_NonLiteralDefault" not in stub

    def test_overload_params_preserved_runtime(self, tmp_path):
        """Runtime: overload variant annotations not replaced by implementation."""
        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def parse(x: int) -> int: ...
            @overload
            def parse(x: str) -> str: ...
            def parse(x): return x
        """)
        assert "x: int" in stub
        assert "x: str" in stub
        assert stub.count("@overload") == 2

    def test_overload_params_preserved_ast_only(self, tmp_path):
        """AST-only: overload variant annotations come from the variant node."""

        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def convert(value: bytes, encoding: str = "utf-8") -> str: ...
            @overload
            def convert(value: str) -> bytes: ...
            def convert(value, encoding="utf-8"): return value
        """, imports="none")
        assert "value: bytes" in stub
        assert "encoding: str" in stub
        assert "value: str" in stub
        assert stub.count("@overload") == 2

    def test_overload_return_types_preserved(self, tmp_path):
        stub, _ = self._generate(tmp_path, """\
            from typing import overload
            @overload
            def f(x: int) -> int: ...
            @overload
            def f(x: str) -> str: ...
            def f(x): return x
        """)
        assert "-> int" in stub
        assert "-> str" in stub

    def test_warning_for_runtime_uninformative_type(self, tmp_path):
        """Runtime: WARNING when variable has uninformative type (function object)."""
        stub, diags = self._generate(tmp_path, "import os\nPATH = os.getcwd()\nX: int = 1\n")
        warns = [d for d in diags.all
                 if d.level >= Level.WARNING and "PATH" in d.symbol]
        assert warns == []
        assert "PATH: str" in stub

    def test_info_for_ast_only_non_literal_variable(self, tmp_path):
        """AST-only: INFO diagnostic when variable RHS is not a literal."""
        stub, diags = self._generate(
            tmp_path, "import os\nPATH = os.getcwd()\n",
            imports="none",
        )
        infos = [d for d in diags.all
                 if d.level == Level.INFO and "PATH" in d.symbol]
        assert infos, f"Expected INFO for PATH; got {[(d.symbol, d.message) for d in diags.all]}"
        assert "not a literal" in infos[0].message

    def test_no_warning_for_annotated_variable(self, tmp_path):
        """No diagnostic when variable is annotated — type is explicit."""
        _, diags = self._generate(
            tmp_path, "import os\nPATH: str = os.getcwd()\n",
            imports="none",
        )
        warns = [d for d in diags.all
                 if d.level >= Level.WARNING and "PATH" in d.symbol]
        assert not warns, f"Unexpected warning: {warns}"

    def test_no_diagnostic_for_literal_variable(self, tmp_path):
        """No diagnostic for literal-valued variable — type is inferred cleanly."""
        _, diags = self._generate(
            tmp_path, "MAX = 100\nLABEL = 'hello'\n",
            imports="none",
        )
        warns = [d for d in diags.all
                 if d.level >= Level.WARNING
                 and any(n in d.symbol for n in ("MAX", "LABEL"))]
        assert not warns

    def test_import_failure_warns_and_falls_back(self, tmp_path):
        """A failed import is a WARNING and the stub comes from the source."""
        src = "import _nonexistent_module_xyz\nX: int = 1\n"
        stub, diags = self._generate(
            tmp_path, src,
        )
        warns = [d for d in diags.all
                 if d.level >= Level.WARNING
                 and ("falling back" in d.message.lower() or "fallback" in d.message.lower())]
        assert warns, f"Expected WARNING about AST-only fallback; got: {[d.message for d in diags.all]}"
        assert "X: int" in stub

    def test_info_for_bare_param(self, tmp_path):
        """INFO diagnostic when a method param has no annotation or inferrable type."""
        stub, diags = self._generate(tmp_path, """\
            class C:
                def m(self, opaque_value): pass
        """)
        infos = [d for d in diags.all
                 if d.level == Level.INFO and "opaque_value" in d.message]
        assert infos, f"Expected INFO for opaque_value; diags: {[d.message for d in diags.all]}"

    def test_no_info_for_annotated_param(self, tmp_path):
        """No diagnostic for an annotated param."""
        _, diags = self._generate(tmp_path, """\
            class C:
                def m(self, x: int, y: str = "hi") -> None: pass
        """)
        spurious = [d for d in diags.all
                    if d.level == Level.INFO
                    and any(n in d.message for n in ("'x'", "'y'"))]
        assert not spurious

    def test_no_info_for_inferred_param(self, tmp_path):
        """No diagnostic when param type is inferred from literal default."""
        _, diags = self._generate(tmp_path, """\
            class C:
                def m(self, x=0, y="hi", flag=True) -> None: pass
        """)
        spurious = [d for d in diags.all
                    if d.level == Level.INFO
                    and any(n in d.message for n in ("'x'", "'y'", "'flag'"))]
        assert not spurious
