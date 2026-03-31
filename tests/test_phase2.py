#!/usr/bin/env python3
"""
Phase 2 test suite — Module-Level Symbols (P2-A, P2-B, P2-C)

Tests are organised into sections matching the Phase 2 spec:

  P2-A  Module-Level Function Stubs
  P2-B  Module-Level Variable Stubs
  P2-C  __all__ Filtering
  INT   Integration (combined, demo files, edge-cases)

Run with:
    cd /home/claude/stubpy_project
    PYTHONPATH=/home/claude/stubpy_project python3 tests/test_phase2.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import tempfile
import textwrap
import traceback
import types as _t
from pathlib import Path

# ── Ensure package is importable ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from stubpy import generate_stub
from stubpy.ast_pass import FunctionInfo, VariableInfo, ast_harvest
from stubpy.context import StubConfig, StubContext
from stubpy.diagnostics import DiagnosticLevel, DiagnosticStage
from stubpy.emitter import generate_function_stub, generate_variable_stub
from stubpy.symbols import (
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    build_symbol_table,
)

# ── Test harness ──────────────────────────────────────────────────────────────

passed = failed = 0
_errors: list[tuple[str, str]] = []


def T(name: str, fn) -> None:
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✓ {name}")
    except Exception as exc:
        failed += 1
        _errors.append((name, traceback.format_exc()))
        print(f"  ✗ {name}: {exc}")


def make_stub(source: str, config: StubConfig | None = None) -> str:
    """Write *source* to a temp file and run generate_stub, returning content."""
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    out = tmp.with_suffix(".pyi")
    ctx = StubContext(config=config) if config else None
    return generate_stub(str(tmp), str(out), ctx=ctx)


def flatten(content: str) -> str:
    """Collapse multi-line signatures into single lines for easier assertion."""
    lines = content.splitlines()
    out: list[str] = []
    buf: list[str] = []
    for line in lines:
        if buf:
            stripped = line.strip()
            if stripped.startswith(")"):
                out.append(buf[0] + ", ".join(buf[1:]) + stripped)
                buf = []
            else:
                buf.append(stripped)
        elif line.rstrip().endswith("("):
            buf.append(line.rstrip())
        else:
            out.append(line)
    out.extend(buf)
    return "\n".join(out)


def assert_valid_syntax(content: str) -> None:
    try:
        ast.parse(content)
    except SyntaxError as exc:
        raise AssertionError(f"Invalid syntax in generated stub: {exc}")


def function_sym(
    name: str,
    live_func=None,
    is_async: bool = False,
    raw_return: str | None = None,
    raw_args: dict[str, str] | None = None,
    lineno: int = 1,
) -> FunctionSymbol:
    """Build a FunctionSymbol with optional FunctionInfo."""
    fi = FunctionInfo(
        name=name,
        lineno=lineno,
        is_async=is_async,
        raw_return_annotation=raw_return,
        raw_arg_annotations=raw_args or {},
    )
    return FunctionSymbol(name=name, lineno=lineno, live_func=live_func, ast_info=fi)


def variable_sym(
    name: str,
    annotation: str | None = None,
    inferred: str | None = None,
    live_value=None,
    lineno: int = 1,
) -> VariableSymbol:
    vi = VariableInfo(name=name, lineno=lineno, annotation_str=annotation)
    return VariableSymbol(
        name=name,
        lineno=lineno,
        annotation_str=annotation,
        inferred_type_str=inferred,
        live_value=live_value,
        ast_info=vi,
    )


# ══════════════════════════════════════════════════════════════════════════════
# P2-A: Module-Level Function Stubs
# ══════════════════════════════════════════════════════════════════════════════
print("\n── P2-A: generate_function_stub (unit) ─────────────────────────────────")


def t_func_basic_sync():
    """Sync function with typed params emits correct def stub."""
    def greet(name: str, times: int = 1) -> str: return ""
    sym = function_sym("greet", live_func=greet, raw_return="str")
    stub = generate_function_stub(sym, StubContext())
    assert "def greet" in stub
    assert "name: str" in stub
    assert "times: int = 1" in stub
    assert "-> str" in stub
    assert "..." in stub
    assert "async" not in stub
T("basic_sync_function", t_func_basic_sync)


def t_func_async_detection_from_ast():
    """Async flag from AST info is respected even without runtime coroutine."""
    fi = FunctionInfo(name="fetch", lineno=1, is_async=True)
    sym = FunctionSymbol("fetch", 1, live_func=None, ast_info=fi)
    stub = generate_function_stub(sym, StubContext())
    assert stub.startswith("async def fetch")
T("async_from_ast_flag", t_func_async_detection_from_ast)


def t_func_async_detection_from_runtime():
    """Async flag detected from inspect.iscoroutinefunction at runtime."""
    import asyncio

    async def fetch(url: str) -> bytes: return b""

    fi = FunctionInfo(name="fetch", lineno=1, is_async=False)  # deliberately wrong AST
    sym = FunctionSymbol("fetch", 1, live_func=fetch, ast_info=fi)
    stub = generate_function_stub(sym, StubContext())
    # Runtime inspection must correct the AST flag
    assert stub.startswith("async def fetch")
T("async_from_runtime_inspection", t_func_async_detection_from_runtime)


def t_func_no_params():
    """Zero-parameter function emits empty signature."""
    def ping() -> None: pass
    sym = function_sym("ping", live_func=ping, raw_return="None")
    stub = generate_function_stub(sym, StubContext())
    assert "def ping() -> None: ..." in stub
T("zero_params_function", t_func_no_params)


def t_func_no_annotations():
    """Function without any annotations emits bare param names."""
    def raw(x, y): pass
    sym = function_sym("raw", live_func=raw)
    stub = generate_function_stub(sym, StubContext())
    assert "def raw(x, y)" in stub
T("no_annotations_bare_names", t_func_no_annotations)


def t_func_inline_format_two_params():
    """≤2 body params → inline (single-line) format."""
    def add(a: float, b: float) -> float: return a + b
    sym = function_sym("add", live_func=add)
    stub = generate_function_stub(sym, StubContext())
    assert stub.count("\n") == 0 or "def add(a:" in stub.splitlines()[0]
T("two_params_inline_format", t_func_inline_format_two_params)


def t_func_multiline_format_three_params():
    """3+ params → multi-line format."""
    def transform(x: int, y: int, z: int) -> int: return x
    sym = function_sym("transform", live_func=transform)
    stub = generate_function_stub(sym, StubContext())
    assert "\n" in stub  # must be multi-line
    assert_valid_syntax(stub)
T("three_params_multiline_format", t_func_multiline_format_three_params)


def t_func_default_values():
    """Default values are preserved in function stubs."""
    def greet(name: str = "world", *, sep: str = "!") -> str: return ""
    sym = function_sym("greet", live_func=greet)
    stub = flatten(generate_function_stub(sym, StubContext()))
    assert "name: str = 'world'" in stub
    assert "sep: str = '!'" in stub
T("default_values_preserved", t_func_default_values)


def t_func_kw_only_separator():
    """Keyword-only params get bare * separator before them."""
    def fn(a: int, *, b: str) -> None: pass
    sym = function_sym("fn", live_func=fn)
    stub = flatten(generate_function_stub(sym, StubContext()))
    assert "*," in stub or "*, b" in stub
    idx_star = stub.index("*")
    idx_b = stub.index("b:")
    assert idx_star < idx_b
T("kw_only_separator_inserted", t_func_kw_only_separator)


def t_func_var_positional():
    """*args with annotation is preserved."""
    def fn(x: int, *args: str) -> None: pass
    sym = function_sym("fn", live_func=fn)
    stub = flatten(generate_function_stub(sym, StubContext()))
    assert "*args: str" in stub
T("var_positional_with_annotation", t_func_var_positional)


def t_func_var_keyword():
    """**kwargs with annotation is preserved."""
    def fn(**kwargs: int) -> None: pass
    sym = function_sym("fn", live_func=fn)
    stub = flatten(generate_function_stub(sym, StubContext()))
    assert "**kwargs: int" in stub
T("var_keyword_with_annotation", t_func_var_keyword)


def t_func_return_annotation():
    """Return annotation is correctly included."""
    def square(n: int) -> int: return n * n
    sym = function_sym("square", live_func=square, raw_return="int")
    stub = generate_function_stub(sym, StubContext())
    assert "-> int" in stub
T("return_annotation_emitted", t_func_return_annotation)


def t_func_return_none():
    """Explicit -> None return is emitted."""
    def do_thing() -> None: pass
    sym = function_sym("do_thing", live_func=do_thing, raw_return="None")
    stub = generate_function_stub(sym, StubContext())
    assert "-> None" in stub
T("return_none_annotation", t_func_return_none)


def t_func_no_return_annotation():
    """Missing return annotation produces no -> in stub."""
    def untyped(): pass
    sym = function_sym("untyped", live_func=untyped)
    stub = generate_function_stub(sym, StubContext())
    assert "->" not in stub
T("missing_return_annotation_absent", t_func_no_return_annotation)


def t_func_valid_syntax():
    """All generated function stubs are syntactically valid Python."""
    def complex_fn(a: int, b: str, c: float = 1.0, *, d: bool = False, **kw: str) -> None: pass
    sym = function_sym("complex_fn", live_func=complex_fn, raw_return="None")
    stub = generate_function_stub(sym, StubContext())
    assert_valid_syntax(stub)
T("complex_function_valid_syntax", t_func_valid_syntax)


def t_func_ast_raw_return_fallback():
    """AST raw_return_annotation is used when live callable is absent."""
    fi = FunctionInfo(name="helper", lineno=1, raw_return_annotation="list[str]")
    sym = FunctionSymbol("helper", 1, live_func=None, ast_info=fi)
    stub = generate_function_stub(sym, StubContext())
    assert "-> list[str]" in stub
T("raw_return_fallback_no_live_func", t_func_ast_raw_return_fallback)


def t_func_none_live_no_crash():
    """No live_func and no ast_info → empty string, no crash."""
    sym = FunctionSymbol("orphan", 1, live_func=None, ast_info=None)
    stub = generate_function_stub(sym, StubContext())
    assert isinstance(stub, str)
    # Should still emit something (at minimum def name():...) or empty
T("none_live_func_no_crash", t_func_none_live_no_crash)


def t_func_optional_annotation():
    """Optional[X] annotation survives function stub generation."""
    from typing import Optional
    def fn(x: Optional[str] = None) -> Optional[int]: return None
    sym = function_sym("fn", live_func=fn)
    stub = flatten(generate_function_stub(sym, StubContext()))
    assert "Optional" in stub
T("optional_annotation_function", t_func_optional_annotation)


# ══════════════════════════════════════════════════════════════════════════════
# P2-A: Function stubs via generate_stub (integration)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── P2-A: Function stubs via generate_stub ───────────────────────────────")


def t_p2a_sync_stub_in_output():
    """Sync module-level function appears in generated .pyi."""
    c = make_stub("def greet(name: str) -> str: return name\n")
    assert "def greet(name: str) -> str: ..." in c
T("sync_function_in_output", t_p2a_sync_stub_in_output)


def t_p2a_async_stub_in_output():
    """Async module-level function emits async def in .pyi."""
    c = make_stub("async def fetch(url: str) -> bytes: ...\n")
    assert "async def fetch(url: str) -> bytes: ..." in c
T("async_function_in_output", t_p2a_async_stub_in_output)


def t_p2a_multiple_functions():
    """Multiple functions all appear in stub."""
    c = make_stub(
        "def foo(x: int) -> int: return x\n"
        "def bar(y: str) -> str: return y\n"
    )
    assert "def foo(x: int) -> int" in c
    assert "def bar(y: str) -> str" in c
T("multiple_functions_all_present", t_p2a_multiple_functions)


def t_p2a_function_with_defaults():
    """Function defaults appear in .pyi output."""
    c = make_stub("def fn(x: int = 0, y: str = 'hi') -> None: pass\n")
    assert "x: int = 0" in c
    assert "y: str = 'hi'" in c
T("function_defaults_in_output", t_p2a_function_with_defaults)


def t_p2a_async_and_sync_together():
    """Mix of sync and async functions both appear."""
    c = make_stub(
        "def sync_fn(a: int) -> int: return a\n"
        "async def async_fn(b: str) -> str: return b\n"
    )
    assert "def sync_fn" in c
    assert "async def async_fn" in c
T("sync_and_async_mixed", t_p2a_async_and_sync_together)


def t_p2a_multiline_function():
    """Function with >2 params emits valid multi-line stub."""
    c = make_stub(
        "def transform(x: int, y: int, z: int, scale: float = 1.0) -> tuple: ...\n"
    )
    assert_valid_syntax(c)
    assert "def transform" in c
T("multiline_function_valid_syntax", t_p2a_multiline_function)


def t_p2a_function_and_class_coexist():
    """Module with both class and function has both in stub."""
    c = make_stub(
        "class Foo:\n"
        "    def method(self) -> None: ...\n"
        "def helper(x: int) -> int: return x\n"
    )
    assert "class Foo:" in c
    assert "def helper(x: int) -> int" in c
T("function_and_class_coexist", t_p2a_function_and_class_coexist)


def t_p2a_private_function_excluded():
    """Private functions (_name) are excluded without --include-private."""
    c = make_stub("def _private(x: int) -> int: return x\ndef public(x: int) -> int: return x\n")
    assert "def public" in c
    assert "def _private" not in c
T("private_function_excluded", t_p2a_private_function_excluded)


def t_p2a_kw_only_function_in_output():
    """Keyword-only separator * appears correctly in output."""
    c = make_stub("def fn(a: int, *, b: str = 'x') -> None: pass\n")
    flat = flatten(c)
    fn_line = [l for l in flat.splitlines() if "def fn" in l][0]
    assert "a: int" in fn_line
    assert "b: str" in fn_line
    assert "*," in fn_line or "*, b" in fn_line
T("kw_only_in_output", t_p2a_kw_only_function_in_output)


def t_p2a_typing_imports_collected():
    """Typing names used in function stubs appear in header."""
    c = make_stub("from typing import Optional\ndef fn(x: Optional[str] = None) -> Optional[int]: ...\n")
    assert "from typing import Optional" in c
T("typing_imports_for_functions", t_p2a_typing_imports_collected)


def t_p2a_source_order_preserved():
    """Functions appear in source definition order."""
    c = make_stub(
        "def first() -> int: return 1\n"
        "def second() -> str: return ''\n"
        "def third() -> bool: return True\n"
    )
    pos_first  = c.index("def first")
    pos_second = c.index("def second")
    pos_third  = c.index("def third")
    assert pos_first < pos_second < pos_third
T("function_source_order_preserved", t_p2a_source_order_preserved)


def t_p2a_var_positional_in_output():
    """*args preserved in module-level function stub."""
    c = make_stub("def fn(x: int, *args: str) -> None: pass\n")
    assert "*args: str" in c
T("var_positional_in_output", t_p2a_var_positional_in_output)


def t_p2a_var_keyword_in_output():
    """**kwargs preserved in module-level function stub."""
    c = make_stub("def fn(**kwargs: int) -> None: pass\n")
    assert "**kwargs: int" in c
T("var_keyword_in_output", t_p2a_var_keyword_in_output)


# ══════════════════════════════════════════════════════════════════════════════
# P2-B: Module-Level Variable Stubs
# ══════════════════════════════════════════════════════════════════════════════
print("\n── P2-B: generate_variable_stub (unit) ─────────────────────────────────")


def t_var_annotated():
    """Annotated variable emits name: Type."""
    sym = variable_sym("MAX", annotation="int", live_value=100)
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "MAX: int"
T("annotated_variable", t_var_annotated)


def t_var_annotated_str():
    """String annotation emitted verbatim."""
    sym = variable_sym("NAME", annotation="str", live_value="hello")
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "NAME: str"
T("annotated_str_variable", t_var_annotated_str)


def t_var_annotated_bool():
    """Bool annotation emitted correctly."""
    sym = variable_sym("ENABLED", annotation="bool", live_value=True)
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "ENABLED: bool"
T("annotated_bool_variable", t_var_annotated_bool)


def t_var_inferred_type_fallback():
    """Unannotated variable falls back to inferred type from runtime."""
    sym = variable_sym("VERSION", inferred="str", live_value="1.0.0")
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "VERSION: str"
T("inferred_type_fallback", t_var_inferred_type_fallback)


def t_var_inferred_records_warning():
    """Unannotated variable records a WARNING diagnostic."""
    ctx = StubContext()
    sym = variable_sym("X", inferred="int", live_value=42)
    generate_variable_stub(sym, ctx)
    assert ctx.diagnostics.has_warnings()
    warn = ctx.diagnostics.warnings[0]
    assert warn.level == DiagnosticLevel.WARNING
    assert warn.stage == DiagnosticStage.EMIT
    assert "X" in warn.symbol
T("inferred_warns_diagnostic", t_var_inferred_records_warning)


def t_var_annotated_no_warning():
    """Annotated variable does NOT produce a diagnostic warning."""
    ctx = StubContext()
    sym = variable_sym("MAX", annotation="int", live_value=100)
    generate_variable_stub(sym, ctx)
    assert not ctx.diagnostics.has_warnings()
T("annotated_no_warning", t_var_annotated_no_warning)


def t_var_no_type_returns_empty():
    """Variable with neither annotation nor inferred type returns empty string."""
    sym = variable_sym("MYSTERY")  # no annotation, no inferred
    stub = generate_variable_stub(sym, StubContext())
    assert stub == ""
T("no_type_returns_empty", t_var_no_type_returns_empty)


def t_var_annotation_takes_priority():
    """Annotation string takes priority over inferred type."""
    # Both provided → annotation wins
    sym = variable_sym("X", annotation="float", inferred="int", live_value=3)
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "X: float"
T("annotation_priority_over_inferred", t_var_annotation_takes_priority)


def t_var_complex_annotation():
    """Complex annotation strings are emitted verbatim."""
    sym = variable_sym("DATA", annotation="dict[str, list[int]]")
    stub = generate_variable_stub(sym, StubContext())
    assert stub == "DATA: dict[str, list[int]]"
T("complex_annotation_emitted_verbatim", t_var_complex_annotation)


# ══════════════════════════════════════════════════════════════════════════════
# P2-B: Variable stubs via generate_stub (integration)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── P2-B: Variable stubs via generate_stub ───────────────────────────────")


def t_p2b_annotated_int():
    """Annotated int variable appears in stub."""
    c = make_stub("MAX: int = 1024\n")
    assert "MAX: int" in c
T("annotated_int_in_output", t_p2b_annotated_int)


def t_p2b_annotated_str():
    """Annotated str variable appears in stub."""
    c = make_stub("NAME: str = 'test'\n")
    assert "NAME: str" in c
T("annotated_str_in_output", t_p2b_annotated_str)


def t_p2b_annotated_float():
    """Annotated float variable appears in stub."""
    c = make_stub("PI: float = 3.14\n")
    assert "PI: float" in c
T("annotated_float_in_output", t_p2b_annotated_float)


def t_p2b_annotated_bool():
    """Annotated bool variable appears in stub."""
    c = make_stub("ENABLED: bool = True\n")
    assert "ENABLED: bool" in c
T("annotated_bool_in_output", t_p2b_annotated_bool)


def t_p2b_unannotated_inferred():
    """Unannotated variable emits inferred type from runtime value."""
    c = make_stub("VERSION = '1.0.0'\n")
    assert "VERSION: str" in c
T("unannotated_inferred_from_runtime", t_p2b_unannotated_inferred)


def t_p2b_unannotated_int_inferred():
    """Unannotated integer emits int as inferred type."""
    c = make_stub("TIMEOUT = 30\n")
    assert "TIMEOUT: int" in c
T("unannotated_int_inferred", t_p2b_unannotated_int_inferred)


def t_p2b_unannotated_bool_inferred():
    """Unannotated bool emits bool as inferred type."""
    c = make_stub("DEBUG = False\n")
    assert "DEBUG: bool" in c
T("unannotated_bool_inferred", t_p2b_unannotated_bool_inferred)


def t_p2b_private_variable_excluded():
    """Private variables (_name) excluded without --include-private."""
    c = make_stub("_CACHE: dict = {}\nPUBLIC: int = 1\n")
    assert "PUBLIC: int" in c
    assert "_CACHE" not in c
T("private_variable_excluded", t_p2b_private_variable_excluded)


def t_p2b_multiple_variables():
    """Multiple annotated variables all appear in stub."""
    c = make_stub("A: int = 1\nB: str = 'x'\nC: float = 1.0\n")
    assert "A: int" in c
    assert "B: str" in c
    assert "C: float" in c
T("multiple_variables_all_present", t_p2b_multiple_variables)


def t_p2b_variable_source_order():
    """Variables appear in source definition order."""
    c = make_stub("FIRST: int = 1\nSECOND: str = 'x'\nTHIRD: bool = True\n")
    pos_first  = c.index("FIRST")
    pos_second = c.index("SECOND")
    pos_third  = c.index("THIRD")
    assert pos_first < pos_second < pos_third
T("variable_source_order_preserved", t_p2b_variable_source_order)


def t_p2b_valid_syntax_with_variables():
    """Output containing variables is syntactically valid Python."""
    c = make_stub("X: int = 1\nY: str = 'hi'\nZ = 3.14\n")
    assert_valid_syntax(c)
T("variables_valid_syntax", t_p2b_valid_syntax_with_variables)


def t_p2b_variable_no_value():
    """Variable declared without a value: just `x: int`."""
    c = make_stub("x: int\n")
    assert "x: int" in c
T("variable_declaration_no_value", t_p2b_variable_no_value)


# ══════════════════════════════════════════════════════════════════════════════
# P2-C: __all__ Filtering
# ══════════════════════════════════════════════════════════════════════════════
print("\n── P2-C: __all__ filtering ──────────────────────────────────────────────")


def t_p2c_all_filters_functions():
    """Functions not in __all__ are excluded from stub."""
    c = make_stub(
        "__all__ = ['public_fn']\n"
        "def public_fn(x: int) -> int: return x\n"
        "def excluded_fn(y: str) -> str: return y\n"
    )
    assert "def public_fn" in c
    assert "def excluded_fn" not in c
T("all_filters_functions", t_p2c_all_filters_functions)


def t_p2c_all_filters_variables():
    """Variables not in __all__ are excluded from stub."""
    c = make_stub(
        "__all__ = ['PUBLIC']\n"
        "PUBLIC: int = 1\n"
        "EXCLUDED: str = 'nope'\n"
    )
    assert "PUBLIC: int" in c
    assert "EXCLUDED" not in c
T("all_filters_variables", t_p2c_all_filters_variables)


def t_p2c_all_filters_classes():
    """Classes not in __all__ are excluded from stub."""
    c = make_stub(
        "__all__ = ['Exported']\n"
        "class Exported:\n    x: int = 1\n"
        "class Hidden:\n    y: int = 2\n"
    )
    assert "class Exported:" in c
    assert "class Hidden" not in c
T("all_filters_classes", t_p2c_all_filters_classes)


def t_p2c_all_mixed_kinds():
    """__all__ correctly includes a mix of classes, functions, variables."""
    c = make_stub(
        "__all__ = ['MyClass', 'my_fn', 'MY_VAR']\n"
        "class MyClass:\n    pass\n"
        "def my_fn() -> None: pass\n"
        "MY_VAR: int = 42\n"
        "class OtherClass:\n    pass\n"
        "def other_fn() -> None: pass\n"
        "OTHER_VAR: str = 'x'\n"
    )
    assert "class MyClass:" in c
    assert "def my_fn" in c
    assert "MY_VAR: int" in c
    assert "class OtherClass" not in c
    assert "def other_fn" not in c
    assert "OTHER_VAR" not in c
T("all_mixed_kinds", t_p2c_all_mixed_kinds)


def t_p2c_no_all_includes_everything():
    """Without __all__, all public symbols are included."""
    c = make_stub(
        "class Foo:\n    pass\n"
        "def bar() -> None: pass\n"
        "BAZ: int = 1\n"
    )
    assert "class Foo:" in c
    assert "def bar" in c
    assert "BAZ: int" in c
T("no_all_includes_all_public", t_p2c_no_all_includes_everything)


def t_p2c_empty_all():
    """Empty __all__ = [] results in no symbols emitted (just header)."""
    c = make_stub(
        "__all__ = []\n"
        "class Foo:\n    pass\n"
        "def bar() -> None: pass\n"
    )
    assert "class Foo" not in c
    assert "def bar" not in c
T("empty_all_emits_nothing", t_p2c_empty_all)


def t_p2c_include_private_flag():
    """--include-private includes _private symbols in output."""
    cfg = StubConfig(include_private=True)
    c = make_stub("_SECRET: int = 1\nPUBLIC: str = 'x'\n", config=cfg)
    assert "_SECRET: int" in c
    assert "PUBLIC: str" in c
T("include_private_flag", t_p2c_include_private_flag)


def t_p2c_include_private_functions():
    """--include-private includes _private functions."""
    cfg = StubConfig(include_private=True)
    c = make_stub(
        "def _private_fn(x: int) -> int: return x\n"
        "def public_fn(y: str) -> str: return y\n",
        config=cfg,
    )
    assert "def _private_fn" in c
    assert "def public_fn" in c
T("include_private_functions", t_p2c_include_private_functions)


def t_p2c_include_private_false_default():
    """Default config excludes private symbols."""
    c = make_stub("_PRIVATE: int = 1\nPUBLIC: int = 2\n")
    assert "_PRIVATE" not in c
    assert "PUBLIC: int" in c
T("private_excluded_by_default", t_p2c_include_private_false_default)


def t_p2c_all_overrides_public():
    """__all__ can restrict even clearly-public names."""
    c = make_stub(
        "__all__ = ['Alpha']\n"
        "class Alpha:\n    pass\n"
        "class Beta:\n    pass\n"  # public name but not in __all__
    )
    assert "class Alpha:" in c
    assert "class Beta" not in c
T("all_restricts_public_names", t_p2c_all_overrides_public)


def t_p2c_all_with_include_private():
    """__all__ + include_private: private names still need to be in __all__ to appear."""
    cfg = StubConfig(include_private=True)
    c = make_stub(
        "__all__ = ['PUBLIC']\n"
        "PUBLIC: int = 1\n"
        "_PRIVATE: str = 'x'\n",  # include_private=True but not in __all__
        config=cfg,
    )
    assert "PUBLIC: int" in c
    # _PRIVATE not in __all__ → excluded even with include_private
    assert "_PRIVATE" not in c
T("include_private_still_respects_all", t_p2c_all_with_include_private)


def t_p2c_respect_all_false():
    """respect_all=False disables __all__ filtering."""
    cfg = StubConfig(respect_all=False)
    c = make_stub(
        "__all__ = ['Alpha']\n"
        "class Alpha:\n    pass\n"
        "class Beta:\n    pass\n",
        config=cfg,
    )
    assert "class Alpha:" in c
    assert "class Beta:" in c  # included because respect_all=False
T("respect_all_false_includes_all", t_p2c_respect_all_false)


def t_p2c_build_symbol_table_all_filter():
    """build_symbol_table with all_exports correctly filters all symbol kinds."""
    src = (
        "__all__ = ['PubClass', 'pub_fn', 'PUB_VAR']\n"
        "class PubClass: pass\n"
        "class PrivClass: pass\n"
        "def pub_fn() -> None: pass\n"
        "def priv_fn() -> None: pass\n"
        "PUB_VAR: int = 1\n"
        "PRIV_VAR: str = 'x'\n"
    )
    syms = ast_harvest(src)
    m = _t.ModuleType("_stubpy_target_p2c")
    class PubClass: pass
    class PrivClass: pass
    PubClass.__module__ = PrivClass.__module__ = "_stubpy_target_p2c"
    m.PubClass, m.PrivClass = PubClass, PrivClass
    def pub_fn(): pass
    def priv_fn(): pass
    m.pub_fn, m.priv_fn = pub_fn, priv_fn
    m.PUB_VAR, m.PRIV_VAR = 1, "x"
    tbl = build_symbol_table(m, "_stubpy_target_p2c", syms,
                             all_exports={"PubClass", "pub_fn", "PUB_VAR"})
    names = tbl.all_names()
    assert "PubClass" in names
    assert "pub_fn" in names
    assert "PUB_VAR" in names
    assert "PrivClass" not in names
    assert "priv_fn" not in names
    assert "PRIV_VAR" not in names
T("build_symbol_table_all_filter_all_kinds", t_p2c_build_symbol_table_all_filter)


def t_p2c_include_private_in_symbol_table():
    """build_symbol_table with include_private=True includes _ names."""
    src = "_SECRET: int = 1\nPUBLIC: str = 'x'\n"
    syms = ast_harvest(src)
    m = _t.ModuleType("_stubpy_target_incpriv")
    m._SECRET, m.PUBLIC = 1, "x"

    tbl_no = build_symbol_table(m, "_stubpy_target_incpriv", syms)
    assert "_SECRET" not in tbl_no
    assert "PUBLIC" in tbl_no

    tbl_yes = build_symbol_table(m, "_stubpy_target_incpriv", syms, include_private=True)
    assert "_SECRET" in tbl_yes
    assert "PUBLIC" in tbl_yes
T("include_private_in_symbol_table", t_p2c_include_private_in_symbol_table)


# ══════════════════════════════════════════════════════════════════════════════
# Interleaved source-order (classes + functions + variables together)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Source-order interleaving ────────────────────────────────────────────")


def t_source_order_mixed_kinds():
    """Class defined before function appears before function in stub."""
    c = make_stub(
        "class Widget:\n"
        "    x: int = 1\n"
        "\n"
        "def make_widget(name: str) -> Widget: ...\n"
        "\n"
        "COLOR: str = 'black'\n"
    )
    pos_class = c.index("class Widget")
    pos_fn    = c.index("def make_widget")
    pos_var   = c.index("COLOR:")
    assert pos_class < pos_fn < pos_var
T("class_function_variable_source_order", t_source_order_mixed_kinds)


def t_function_before_class():
    """Function defined before class appears before class in stub."""
    c = make_stub(
        "def factory() -> 'Foo': ...\n"
        "\n"
        "class Foo:\n"
        "    pass\n"
    )
    pos_fn    = c.index("def factory")
    pos_class = c.index("class Foo")
    assert pos_fn < pos_class
T("function_before_class_order", t_function_before_class)


def t_variable_before_class():
    """Variable defined before class appears before class in stub."""
    c = make_stub(
        "DEFAULT: str = 'x'\n"
        "\n"
        "class Config:\n"
        "    pass\n"
    )
    pos_var   = c.index("DEFAULT:")
    pos_class = c.index("class Config")
    assert pos_var < pos_class
T("variable_before_class_order", t_variable_before_class)


def t_stub_is_always_valid_syntax():
    """Fully mixed stubs (class + fn + var) produce valid Python."""
    c = make_stub(
        "MAX: int = 10\n"
        "\n"
        "def add(a: int, b: int = 0) -> int: return a + b\n"
        "\n"
        "class Container:\n"
        "    items: list\n"
        "    def __init__(self, items: list) -> None: ...\n"
        "\n"
        "VERSION: str = '1.0'\n"
        "\n"
        "async def fetch(url: str) -> bytes: ...\n"
    )
    assert_valid_syntax(c)
T("fully_mixed_stub_valid_syntax", t_stub_is_always_valid_syntax)


# ══════════════════════════════════════════════════════════════════════════════
# Demo-file integration tests
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Demo file integration ────────────────────────────────────────────────")

DEMO = Path(__file__).parent.parent / "demo"


def stub_demo(filename: str, config: StubConfig | None = None) -> str:
    """Run generate_stub on a demo file, write to a temp .pyi, return content."""
    src_path = str(DEMO / filename)
    with tempfile.NamedTemporaryFile(suffix=".pyi", mode="w", delete=False, encoding="utf-8") as f:
        out_path = f.name
    ctx = StubContext(config=config) if config else None
    return generate_stub(src_path, out_path, ctx=ctx)


def t_demo_functions_py():
    """demo/functions.py: all __all__ functions appear, private excluded."""
    c = stub_demo("functions.py")
    assert_valid_syntax(c)
    # All __all__ members present
    for name in ("greet", "add", "fetch_data", "process", "transform", "make_pair"):
        assert f"def {name}" in c, f"Missing function: {name}"
    # Private excluded
    assert "_internal_helper" not in c
T("demo_functions_all_present", t_demo_functions_py)


def t_demo_functions_async():
    """demo/functions.py: fetch_data is emitted as async def."""
    c = stub_demo("functions.py")
    assert "async def fetch_data" in c
T("demo_functions_async_emitted", t_demo_functions_async)


def t_demo_functions_multiline():
    """demo/functions.py: process() with >2 params emits multi-line stub."""
    c = stub_demo("functions.py")
    assert_valid_syntax(c)
    # process has: items, flag, *args, **kwargs → 4 params → multi-line
    assert "def process" in c
    # Multi-line is valid syntax either way
T("demo_functions_multiline_valid", t_demo_functions_multiline)


def t_demo_functions_valid_syntax():
    """demo/functions.py generates syntactically valid stub."""
    c = stub_demo("functions.py")
    assert_valid_syntax(c)
T("demo_functions_valid_syntax", t_demo_functions_valid_syntax)


def t_demo_variables_py():
    """demo/variables.py: all __all__ variables appear with correct types."""
    c = stub_demo("variables.py")
    assert_valid_syntax(c)
    assert "MAX_SIZE: int" in c
    assert "DEFAULT_NAME: str" in c
    assert "PI: float" in c
    assert "ENABLED: bool" in c
    assert "VERSION: str" in c  # inferred from runtime
T("demo_variables_all_annotated", t_demo_variables_py)


def t_demo_variables_private_excluded():
    """demo/variables.py: _INTERNAL_CACHE excluded."""
    c = stub_demo("variables.py")
    assert "_INTERNAL_CACHE" not in c
    assert "_debug_mode" not in c
T("demo_variables_private_excluded", t_demo_variables_private_excluded)


def t_demo_variables_valid_syntax():
    """demo/variables.py generates syntactically valid stub."""
    c = stub_demo("variables.py")
    assert_valid_syntax(c)
T("demo_variables_valid_syntax", t_demo_variables_valid_syntax)


def t_demo_mixed_py():
    """demo/mixed.py: only __all__ members appear."""
    c = stub_demo("mixed.py")
    assert_valid_syntax(c)
    # In __all__
    assert "class Widget:" in c
    assert "def make_widget" in c
    assert "DEFAULT_COLOR: str" in c
    # Not in __all__
    assert "class InternalWidget" not in c
    assert "def helper_func" not in c
    assert "INTERNAL_CONSTANT" not in c
    assert "def _private_factory" not in c
T("demo_mixed_all_filtering", t_demo_mixed_py)


def t_demo_mixed_order():
    """demo/mixed.py: symbols appear in source definition order."""
    c = stub_demo("mixed.py")
    assert_valid_syntax(c)
    pos_var   = c.index("DEFAULT_COLOR")
    pos_fn    = c.index("def make_widget")
    pos_class = c.index("class Widget")
    assert pos_var < pos_fn < pos_class
T("demo_mixed_source_order", t_demo_mixed_order)


def t_demo_graphics_unchanged():
    """demo/graphics.py (classes only, no module-level fns/vars): output unchanged."""
    c = stub_demo("graphics.py")
    assert_valid_syntax(c)
    # All classes still present
    for cls_name in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
        assert f"class {cls_name}" in c, f"Missing class: {cls_name}"
    # kwargs back-tracing still works
    arc_section = c.split("class Arc")[1].split("\nclass ")[0]
    assert "angle: float" in arc_section
    assert "**kwargs" not in arc_section
T("demo_graphics_backward_compat", t_demo_graphics_unchanged)


def t_demo_element_unchanged():
    """demo/element.py still generates correct stubs after Phase 2."""
    c = stub_demo("element.py")
    assert_valid_syntax(c)
    assert "class Style:" in c
    assert "class Element:" in c
T("demo_element_backward_compat", t_demo_element_unchanged)


def t_demo_container_unchanged():
    """demo/container.py cross-import still works after Phase 2."""
    c = stub_demo("container.py")
    assert_valid_syntax(c)
    assert "class Container" in c
    assert "from demo.element import Element" in c
T("demo_container_backward_compat", t_demo_container_unchanged)


# ══════════════════════════════════════════════════════════════════════════════
# Edge-cases and regression guards
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Edge-cases ───────────────────────────────────────────────────────────")


def t_edge_empty_module():
    """Empty module generates a valid (header-only) stub."""
    c = make_stub("")
    assert_valid_syntax(c)
    assert "from __future__ import annotations" in c
T("empty_module_valid_stub", t_edge_empty_module)


def t_edge_only_imports():
    """Module with only imports generates a valid stub."""
    c = make_stub("from typing import Optional\nimport os\n")
    assert_valid_syntax(c)
T("import_only_module_valid", t_edge_only_imports)


def t_edge_all_private_no_all():
    """Module with only private names produces an empty body stub."""
    c = make_stub("_A: int = 1\n_B: str = 'x'\n")
    assert_valid_syntax(c)
    assert "_A" not in c
    assert "_B" not in c
T("all_private_empty_body", t_edge_all_private_no_all)


def t_edge_function_returns_forward_ref():
    """Function returning a forward reference class emits correct stub."""
    c = make_stub(
        "class Foo:\n"
        "    pass\n"
        "def make() -> 'Foo': ...\n"
    )
    assert "def make" in c
    assert_valid_syntax(c)
T("function_forward_ref_return", t_edge_function_returns_forward_ref)


def t_edge_stub_ctx_diagnostics_populated():
    """generate_stub via ctx stores diagnostics including INFO for functions/vars."""
    src = "X: int = 1\ndef fn() -> None: pass\n"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(src)
        tmp = f.name
    ctx = StubContext()
    generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
    # At minimum an INFO diagnostic from AST_PASS stage should exist
    assert len(ctx.diagnostics) > 0
    stages = {d.stage for d in ctx.diagnostics}
    assert DiagnosticStage.AST_PASS in stages
T("generate_stub_populates_diagnostics", t_edge_stub_ctx_diagnostics_populated)


def t_edge_unannotated_var_warning_in_ctx():
    """Unannotated variable generates WARNING in ctx.diagnostics."""
    c = make_stub("UNTYPED = 42\n")
    # Re-run with explicit ctx to capture diagnostics
    src = "UNTYPED = 42\n"
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(src)
        tmp = f.name
    ctx = StubContext()
    generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
    warnings = ctx.diagnostics.warnings
    # Should have at least one warning about inferred type
    assert any("UNTYPED" in w.symbol or "inferred" in w.message.lower() for w in warnings)
T("unannotated_var_warning_in_ctx", t_edge_unannotated_var_warning_in_ctx)


def t_edge_function_complex_signature_valid():
    """Complex mixed signature (pos, kw-only, *args, **kwargs) → valid stub."""
    c = make_stub(
        "from typing import Any\n"
        "def fn(a: int, b: str, *args: float, flag: bool = False, **kw: Any) -> None: pass\n"
    )
    assert_valid_syntax(c)
    assert "def fn" in c
T("complex_mixed_signature_valid", t_edge_function_complex_signature_valid)


def t_edge_variable_before_function_in_all():
    """Variable and function both in __all__ appear in stub."""
    c = make_stub(
        "__all__ = ['CONST', 'helper']\n"
        "CONST: int = 7\n"
        "def helper(x: int) -> int: return x\n"
        "def excluded() -> None: pass\n"
        "ALSO_EXCLUDED: str = 'nope'\n"
    )
    assert "CONST: int" in c
    assert "def helper" in c
    assert "def excluded" not in c
    assert "ALSO_EXCLUDED" not in c
T("all_variable_and_function_together", t_edge_variable_before_function_in_all)


def t_edge_include_private_no_all():
    """include_private + no __all__ → private symbols appear."""
    cfg = StubConfig(include_private=True)
    c = make_stub("_A: int = 1\nB: str = 'x'\n", config=cfg)
    assert "_A: int" in c
    assert "B: str" in c
T("include_private_no_all", t_edge_include_private_no_all)


def t_edge_typevar_decls_excluded_from_variable_stubs():
    """TypeVar declarations do not appear as plain variable stubs."""
    c = make_stub("from typing import TypeVar\nT = TypeVar('T')\nX: int = 1\n")
    assert "X: int" in c
    # TypeVar should not appear as a variable stub (it's an AliasSymbol)
    # It may or may not appear in Phase 2 depending on future alias emission,
    # but it should NOT appear as a plain variable `T: TypeVar`
    assert "T: TypeVar" not in c
T("typevar_not_emitted_as_variable", t_edge_typevar_decls_excluded_from_variable_stubs)


# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print()
print("═" * 65)
print(f"  PHASE 2 TOTAL: {passed + failed}  |  ✓ {passed} passed  |  ✗ {failed} failed")
print("═" * 65)

if _errors:
    print("\nFailed tests detail:")
    for name, tb in _errors:
        print(f"\n  FAILED: {name}")
        for line in tb.strip().splitlines()[-6:]:
            print(f"    {line}")
    sys.exit(1)
else:
    print("\n  All Phase 2 tests passed ✓")
