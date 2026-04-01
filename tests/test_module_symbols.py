"""
tests/test_module_symbols.py
----------------------------
Tests for module-level symbol stub generation:
  - Module-level function stubs (sync, async, overloaded, edge-cases)
  - Module-level variable stubs (annotated, inferred, edge-cases)
  - ``__all__`` filtering across all symbol kinds
  - ``--include-private`` / ``include_private`` config option
  - Source-order interleaving of mixed symbol kinds
"""
from __future__ import annotations

import types as _t


from tests.conftest import assert_valid_syntax, flatten, make_stub
from stubpy.ast_pass import FunctionInfo, VariableInfo, ast_harvest
from stubpy.context import StubConfig, StubContext
from stubpy.diagnostics import DiagnosticLevel, DiagnosticStage
from stubpy.emitter import generate_function_stub, generate_variable_stub
from stubpy.symbols import (
    FunctionSymbol,
    VariableSymbol,
    build_symbol_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _function_sym(
    name: str,
    live_func=None,
    is_async: bool = False,
    raw_return: str | None = None,
    raw_args: dict[str, str] | None = None,
    lineno: int = 1,
) -> FunctionSymbol:
    fi = FunctionInfo(
        name=name,
        lineno=lineno,
        is_async=is_async,
        raw_return_annotation=raw_return,
        raw_arg_annotations=raw_args or {},
    )
    return FunctionSymbol(name=name, lineno=lineno, live_func=live_func, ast_info=fi)


def _variable_sym(
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


def _make_stub_with_config(source: str, **cfg_kwargs) -> str:
    from textwrap import dedent
    import tempfile
    from pathlib import Path
    from stubpy import generate_stub

    source = dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    ctx = StubContext(config=StubConfig(**cfg_kwargs)) if cfg_kwargs else None
    return generate_stub(str(tmp), str(tmp.with_suffix(".pyi")), ctx=ctx)


# ============================================================================
# generate_function_stub — unit tests
# ============================================================================

class TestGenerateFunctionStubUnit:

    def test_basic_sync(self):
        def greet(name: str, times: int = 1) -> str:
            return ""
        sym = _function_sym("greet", live_func=greet, raw_return="str")
        stub = generate_function_stub(sym, StubContext())
        assert "def greet" in stub
        assert "name: str" in stub
        assert "times: int = 1" in stub
        assert "-> str" in stub
        assert "..." in stub
        assert "async" not in stub

    def test_async_from_ast_flag(self):
        fi = FunctionInfo(name="fetch", lineno=1, is_async=True)
        sym = FunctionSymbol("fetch", 1, live_func=None, ast_info=fi)
        assert generate_function_stub(sym, StubContext()).startswith("async def fetch")

    def test_async_detected_from_runtime(self):
        async def fetch(url: str) -> bytes:
            return b""
        fi = FunctionInfo(name="fetch", lineno=1, is_async=False)
        sym = FunctionSymbol("fetch", 1, live_func=fetch, ast_info=fi)
        assert generate_function_stub(sym, StubContext()).startswith("async def fetch")

    def test_zero_params(self):
        def ping() -> None:
            pass
        sym = _function_sym("ping", live_func=ping, raw_return="None")
        assert "def ping() -> None: ..." in generate_function_stub(sym, StubContext())

    def test_no_annotations_bare_names(self):
        def raw(x, y):
            pass
        sym = _function_sym("raw", live_func=raw)
        assert "def raw(x, y)" in generate_function_stub(sym, StubContext())

    def test_inline_for_two_params(self):
        def add(a: float, b: float) -> float:
            return a + b
        sym = _function_sym("add", live_func=add)
        stub = generate_function_stub(sym, StubContext())
        # inline = fits on one line
        assert stub.count("\n") == 0 or "def add(a:" in stub.splitlines()[0]

    def test_multiline_for_three_params(self):
        def transform(x: int, y: int, z: int) -> int:
            return x
        sym = _function_sym("transform", live_func=transform)
        stub = generate_function_stub(sym, StubContext())
        assert "\n" in stub
        assert_valid_syntax(stub)

    def test_default_values_preserved(self):
        def greet(name: str = "world", *, sep: str = "!") -> str:
            return ""
        sym = _function_sym("greet", live_func=greet)
        stub = flatten(generate_function_stub(sym, StubContext()))
        assert "name: str = 'world'" in stub
        assert "sep: str = '!'" in stub

    def test_kw_only_separator(self):
        def fn(a: int, *, b: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        stub = flatten(generate_function_stub(sym, StubContext()))
        assert "*," in stub or "*, b" in stub
        assert stub.index("*") < stub.index("b:")

    def test_var_positional_with_annotation(self):
        def fn(x: int, *args: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        assert "*args: str" in flatten(generate_function_stub(sym, StubContext()))

    def test_var_keyword_with_annotation(self):
        def fn(**kwargs: int) -> None:
            pass
        sym = _function_sym("fn", live_func=fn)
        assert "**kwargs: int" in flatten(generate_function_stub(sym, StubContext()))

    def test_return_annotation(self):
        def square(n: int) -> int:
            return n * n
        sym = _function_sym("square", live_func=square, raw_return="int")
        assert "-> int" in generate_function_stub(sym, StubContext())

    def test_no_return_annotation(self):
        def untyped():
            pass
        sym = _function_sym("untyped", live_func=untyped)
        assert "->" not in generate_function_stub(sym, StubContext())

    def test_raw_return_fallback_no_live_func(self):
        fi = FunctionInfo(name="helper", lineno=1, raw_return_annotation="list[str]")
        sym = FunctionSymbol("helper", 1, live_func=None, ast_info=fi)
        assert "-> list[str]" in generate_function_stub(sym, StubContext())

    def test_no_live_func_no_crash(self):
        sym = FunctionSymbol("orphan", 1, live_func=None, ast_info=None)
        stub = generate_function_stub(sym, StubContext())
        assert isinstance(stub, str)

    def test_complex_signature_valid_syntax(self):
        def fn(a: int, b: str, c: float = 1.0, *, d: bool = False, **kw: str) -> None:
            pass
        sym = _function_sym("fn", live_func=fn, raw_return="None")
        assert_valid_syntax(generate_function_stub(sym, StubContext()))

    def test_async_generator(self):
        async def agen():
            yield 1
        fi = FunctionInfo(name="agen", lineno=1, is_async=False)
        sym = FunctionSymbol("agen", 1, live_func=agen, ast_info=fi)
        assert "async def agen" in generate_function_stub(sym, StubContext())


# ============================================================================
# generate_variable_stub — unit tests
# ============================================================================

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

    def test_inferred_records_warning(self):
        ctx = StubContext()
        sym = _variable_sym("X", inferred="int", live_value=42)
        generate_variable_stub(sym, ctx)
        assert ctx.diagnostics.has_warnings()
        w = ctx.diagnostics.warnings[0]
        assert w.level == DiagnosticLevel.WARNING
        assert w.stage == DiagnosticStage.EMIT
        assert "X" in w.symbol

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


# ============================================================================
# Function stubs via generate_stub
# ============================================================================

class TestFunctionStubGeneration:

    def test_sync_function_in_output(self):
        c = make_stub("def greet(name: str) -> str: return name\n")
        assert "def greet(name: str) -> str: ..." in c

    def test_async_function_in_output(self):
        c = make_stub("async def fetch(url: str) -> bytes: ...\n")
        assert "async def fetch(url: str) -> bytes: ..." in c

    def test_multiple_functions_all_present(self):
        c = make_stub(
            "def foo(x: int) -> int: return x\n"
            "def bar(y: str) -> str: return y\n"
        )
        assert "def foo(x: int) -> int" in c
        assert "def bar(y: str) -> str" in c

    def test_function_defaults_in_output(self):
        c = make_stub("def fn(x: int = 0, y: str = 'hi') -> None: pass\n")
        assert "x: int = 0" in c
        assert "y: str = 'hi'" in c

    def test_sync_and_async_mixed(self):
        c = make_stub(
            "def sync_fn(a: int) -> int: return a\n"
            "async def async_fn(b: str) -> str: return b\n"
        )
        assert "def sync_fn" in c
        assert "async def async_fn" in c

    def test_multiline_valid_syntax(self):
        c = make_stub(
            "def transform(x: int, y: int, z: int, scale: float = 1.0) -> tuple: ...\n"
        )
        assert_valid_syntax(c)
        assert "def transform" in c

    def test_function_and_class_coexist(self):
        c = make_stub(
            "class Foo:\n"
            "    def method(self) -> None: ...\n"
            "def helper(x: int) -> int: return x\n"
        )
        assert "class Foo:" in c
        assert "def helper(x: int) -> int" in c

    def test_private_function_excluded(self):
        c = make_stub(
            "def _private(x: int) -> int: return x\n"
            "def public(x: int) -> int: return x\n"
        )
        assert "def public" in c
        assert "def _private" not in c

    def test_kw_only_separator_in_output(self):
        c = make_stub("def fn(a: int, *, b: str = 'x') -> None: pass\n")
        flat = flatten(c)
        fn_line = [l for l in flat.splitlines() if "def fn" in l][0]
        assert "a: int" in fn_line
        assert "b: str" in fn_line
        assert "*," in fn_line or "*, b" in fn_line

    def test_typing_imports_collected(self):
        c = make_stub(
            "from typing import Optional\n"
            "def fn(x: Optional[str] = None) -> Optional[int]: ...\n"
        )
        assert "from typing import Optional" in c

    def test_source_order_preserved(self):
        c = make_stub(
            "def first() -> int: return 1\n"
            "def second() -> str: return ''\n"
            "def third() -> bool: return True\n"
        )
        assert c.index("def first") < c.index("def second") < c.index("def third")

    def test_var_positional_in_output(self):
        c = make_stub("def fn(x: int, *args: str) -> None: pass\n")
        assert "*args: str" in c

    def test_var_keyword_in_output(self):
        c = make_stub("def fn(**kwargs: int) -> None: pass\n")
        assert "**kwargs: int" in c


# ============================================================================
# Variable stubs via generate_stub
# ============================================================================

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


# ============================================================================
# __all__ filtering
# ============================================================================

class TestAllFiltering:

    def test_filters_functions(self):
        c = make_stub(
            "__all__ = ['public_fn']\n"
            "def public_fn(x: int) -> int: return x\n"
            "def excluded_fn(y: str) -> str: return y\n"
        )
        assert "def public_fn" in c
        assert "def excluded_fn" not in c

    def test_filters_variables(self):
        c = make_stub(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "EXCLUDED: str = 'nope'\n"
        )
        assert "PUBLIC: int" in c
        assert "EXCLUDED" not in c

    def test_filters_classes(self):
        c = make_stub(
            "__all__ = ['Exported']\n"
            "class Exported:\n    x: int = 1\n"
            "class Hidden:\n    y: int = 2\n"
        )
        assert "class Exported:" in c
        assert "class Hidden" not in c

    def test_mixed_kinds(self):
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

    def test_no_all_includes_all_public(self):
        c = make_stub(
            "class Foo:\n    pass\n"
            "def bar() -> None: pass\n"
            "BAZ: int = 1\n"
        )
        assert "class Foo:" in c
        assert "def bar" in c
        assert "BAZ: int" in c

    def test_empty_all_emits_nothing(self):
        c = make_stub(
            "__all__ = []\n"
            "class Foo:\n    pass\n"
            "def bar() -> None: pass\n"
        )
        assert "class Foo" not in c
        assert "def bar" not in c

    def test_all_restricts_public_names(self):
        c = make_stub(
            "__all__ = ['Alpha']\n"
            "class Alpha:\n    pass\n"
            "class Beta:\n    pass\n"
        )
        assert "class Alpha:" in c
        assert "class Beta" not in c

    def test_build_symbol_table_all_filter(self):
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
        m = _t.ModuleType("_stubpy_target_filter")

        class PubClass:
            pass

        class PrivClass:
            pass

        PubClass.__module__ = PrivClass.__module__ = "_stubpy_target_filter"
        m.PubClass, m.PrivClass = PubClass, PrivClass

        def pub_fn():
            pass

        def priv_fn():
            pass

        m.pub_fn, m.priv_fn = pub_fn, priv_fn
        m.PUB_VAR, m.PRIV_VAR = 1, "x"
        tbl = build_symbol_table(
            m, "_stubpy_target_filter", syms,
            all_exports={"PubClass", "pub_fn", "PUB_VAR"},
        )
        names = tbl.all_names()
        assert "PubClass" in names
        assert "pub_fn" in names
        assert "PUB_VAR" in names
        assert "PrivClass" not in names
        assert "priv_fn" not in names
        assert "PRIV_VAR" not in names


# ============================================================================
# include_private
# ============================================================================

class TestIncludePrivate:

    def test_private_variables_included(self):
        c = _make_stub_with_config(
            "_SECRET: int = 1\nPUBLIC: str = 'x'\n",
            include_private=True,
        )
        assert "_SECRET: int" in c
        assert "PUBLIC: str" in c

    def test_private_functions_included(self):
        c = _make_stub_with_config(
            "def _private_fn(x: int) -> int: return x\n"
            "def public_fn(y: str) -> str: return y\n",
            include_private=True,
        )
        assert "def _private_fn" in c
        assert "def public_fn" in c

    def test_private_excluded_by_default(self):
        c = make_stub("_PRIVATE: int = 1\nPUBLIC: int = 2\n")
        assert "_PRIVATE" not in c
        assert "PUBLIC: int" in c

    def test_include_private_in_symbol_table(self):
        src = "_SECRET: int = 1\nPUBLIC: str = 'x'\n"
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_incpriv")
        m._SECRET, m.PUBLIC = 1, "x"

        tbl_default = build_symbol_table(m, "_stubpy_target_incpriv", syms)
        assert "_SECRET" not in tbl_default
        assert "PUBLIC" in tbl_default

        tbl_priv = build_symbol_table(
            m, "_stubpy_target_incpriv", syms, include_private=True
        )
        assert "_SECRET" in tbl_priv
        assert "PUBLIC" in tbl_priv

    def test_include_private_with_all_exports_in_symbol_table(self):
        # When __all__ is present AND include_private=True, private names
        # must appear regardless of __all__, while __all__ still restricts
        # which public names are included.
        src = "__all__ = ['PUB']\nPUB: int = 1\nOTHER: int = 2\n_PRIV: str = 'x'\n"
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_allpriv")
        m.PUB, m.OTHER, m._PRIV = 1, 2, "x"

        # Default: only PUB (in __all__), no private
        tbl = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                 all_exports={"PUB"})
        assert "PUB" in tbl
        assert "OTHER" not in tbl
        assert "_PRIV" not in tbl

        # With include_private: PUB from __all__ + _PRIV private; OTHER still excluded
        tbl_p = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                   all_exports={"PUB"}, include_private=True)
        assert "PUB" in tbl_p
        assert "_PRIV" in tbl_p
        assert "OTHER" not in tbl_p  # public but not in __all__

    def test_include_private_bypasses_all_for_private_names(self):
        # --include-private makes private symbols visible even when __all__
        # is declared and does not list them. __all__ controls public names;
        # include_private controls private ones independently.
        c = _make_stub_with_config(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=True,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE: str" in c  # private appears despite not being in __all__

    def test_include_private_false_still_hides_private_with_all(self):
        # Without the flag, private names stay hidden even if __all__ is absent.
        c = _make_stub_with_config(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=False,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE" not in c

    def test_respect_all_false(self):
        c = _make_stub_with_config(
            "__all__ = ['Alpha']\n"
            "class Alpha:\n    pass\n"
            "class Beta:\n    pass\n",
            respect_all=False,
        )
        assert "class Alpha:" in c
        assert "class Beta:" in c


# ============================================================================
# Source-order interleaving
# ============================================================================

class TestSourceOrder:

    def test_class_function_variable_order(self):
        c = make_stub(
            "class Widget:\n"
            "    x: int = 1\n"
            "\n"
            "def make_widget(name: str) -> Widget: ...\n"
            "\n"
            "COLOR: str = 'black'\n"
        )
        assert c.index("class Widget") < c.index("def make_widget") < c.index("COLOR:")

    def test_function_before_class(self):
        c = make_stub("def factory() -> 'Foo': ...\n\nclass Foo:\n    pass\n")
        assert c.index("def factory") < c.index("class Foo")

    def test_variable_before_class(self):
        c = make_stub("DEFAULT: str = 'x'\n\nclass Config:\n    pass\n")
        assert c.index("DEFAULT:") < c.index("class Config")

    def test_fully_mixed_valid_syntax(self):
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


# ============================================================================
# Edge-cases
# ============================================================================

class TestEdgeCases:

    def test_empty_module(self):
        c = make_stub("")
        assert_valid_syntax(c)
        assert "from __future__ import annotations" in c

    def test_import_only_module(self):
        assert_valid_syntax(make_stub("from typing import Optional\nimport os\n"))

    def test_all_private_empty_body(self):
        c = make_stub("_A: int = 1\n_B: str = 'x'\n")
        assert_valid_syntax(c)
        assert "_A" not in c
        assert "_B" not in c

    def test_function_forward_ref_return(self):
        c = make_stub(
            "class Foo:\n    pass\n"
            "def make() -> 'Foo': ...\n"
        )
        assert "def make" in c
        assert_valid_syntax(c)

    def test_unannotated_var_warning_recorded(self):
        import tempfile
        from pathlib import Path
        from stubpy import generate_stub

        src = "UNTYPED = 42\n"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext()
        generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
        warnings = ctx.diagnostics.warnings
        assert any(
            "UNTYPED" in w.symbol or "inferred" in w.message.lower()
            for w in warnings
        )

    def test_typevar_not_emitted_as_variable(self):
        c = make_stub("from typing import TypeVar\nT = TypeVar('T')\nX: int = 1\n")
        assert "X: int" in c
        assert "T: TypeVar" not in c

    def test_complex_mixed_signature_valid(self):
        c = make_stub(
            "from typing import Any\n"
            "def fn(a: int, b: str, *args: float, flag: bool = False, **kw: Any) -> None: pass\n"
        )
        assert_valid_syntax(c)
        assert "def fn" in c

    def test_variable_and_function_in_all(self):
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
