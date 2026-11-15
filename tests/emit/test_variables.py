"""Tests for module-level variable stubs."""
from __future__ import annotations

from stubpy.analysis.harvest import VariableInfo
from stubpy.analysis.symbols import VariableSymbol
from stubpy.core.context import StubContext
from stubpy.core.diagnostics import Level, Stage
from stubpy.emit import generate_variable_stub
from tests.conftest import (
    assert_valid_syntax,
    make_stub,
)


def _variable_sym(
    name: str,
    annotation: "str | None" = None,
    inferred: "str | None" = None,
    live_value=None,
    lineno: int = 1,
) -> "VariableSymbol":
    vi = VariableInfo(name=name, lineno=lineno, annotation_str=annotation)
    return VariableSymbol(
        name=name, lineno=lineno, annotation_str=annotation,
        inferred_type_str=inferred, live_value=live_value, ast_info=vi,
    )


class TestGenerateVariableStubUnit:

    def test_annotated_int(self):
        sym = _variable_sym("MAX", annotation="int", live_value=100)
        assert generate_variable_stub(sym, StubContext()) == "MAX: int"

    def test_annotated_str(self):
        sym = _variable_sym("NAME", annotation="str", live_value="hello")
        assert generate_variable_stub(sym, StubContext()) == "NAME: str"

    def test_annotated_bool(self):
        sym = _variable_sym("ENABLED", annotation="bool", live_value=True)
        assert generate_variable_stub(sym, StubContext()) == "ENABLED: bool"

    def test_inferred_fallback(self):
        sym = _variable_sym("VERSION", inferred="str", live_value="1.0.0")
        assert generate_variable_stub(sym, StubContext()) == "VERSION: str"

    def test_inferred_records_info(self):
        """Successful inference is INFO, not WARNING — inference working as intended."""
        ctx = StubContext()
        sym = _variable_sym("X", inferred="int", live_value=42)
        generate_variable_stub(sym, ctx)
        assert not ctx.diagnostics.has_warnings(), "Successful inference must not warn"
        assert ctx.diagnostics.has_info()
        info = ctx.diagnostics.info_items[0]
        assert info.level == Level.INFO
        assert info.stage == Stage.EMIT
        assert "X" in info.symbol

    def test_annotated_no_warning(self):
        ctx = StubContext()
        sym = _variable_sym("MAX", annotation="int", live_value=100)
        generate_variable_stub(sym, ctx)
        assert not ctx.diagnostics.has_warnings()

    def test_no_type_returns_empty(self):
        sym = _variable_sym("MYSTERY")
        assert generate_variable_stub(sym, StubContext()) == ""

    def test_annotation_priority_over_inferred(self):
        sym = _variable_sym("X", annotation="float", inferred="int", live_value=3)
        assert generate_variable_stub(sym, StubContext()) == "X: float"

    def test_complex_annotation(self):
        sym = _variable_sym("DATA", annotation="dict[str, list[int]]")
        assert generate_variable_stub(sym, StubContext()) == "DATA: dict[str, list[int]]"


class TestVariableStubGeneration:

    def test_annotated_int(self):
        assert "MAX: int" in make_stub("MAX: int = 1024\n")

    def test_annotated_str(self):
        assert "NAME: str" in make_stub("NAME: str = 'test'\n")

    def test_annotated_float(self):
        assert "PI: float" in make_stub("PI: float = 3.14\n")

    def test_annotated_bool(self):
        assert "ENABLED: bool" in make_stub("ENABLED: bool = True\n")

    def test_unannotated_inferred_str(self):
        assert "VERSION: str" in make_stub("VERSION = '1.0.0'\n")

    def test_unannotated_inferred_int(self):
        assert "TIMEOUT: int" in make_stub("TIMEOUT = 30\n")

    def test_unannotated_inferred_bool(self):
        assert "DEBUG: bool" in make_stub("DEBUG = False\n")

    def test_private_variable_excluded(self):
        c = make_stub("_CACHE: dict = {}\nPUBLIC: int = 1\n")
        assert "PUBLIC: int" in c
        assert "_CACHE" not in c

    def test_multiple_variables_all_present(self):
        c = make_stub("A: int = 1\nB: str = 'x'\nC: float = 1.0\n")
        assert "A: int" in c
        assert "B: str" in c
        assert "C: float" in c

    def test_source_order_preserved(self):
        c = make_stub("FIRST: int = 1\nSECOND: str = 'x'\nTHIRD: bool = True\n")
        assert c.index("FIRST") < c.index("SECOND") < c.index("THIRD")

    def test_valid_syntax(self):
        assert_valid_syntax(make_stub("X: int = 1\nY: str = 'hi'\nZ = 3.14\n"))

    def test_declaration_without_value(self):
        assert "x: int" in make_stub("x: int\n")
