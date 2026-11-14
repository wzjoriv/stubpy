"""Tests for module-level function stubs."""
from __future__ import annotations

from stubpy.analysis.harvest import FunctionInfo
from stubpy.analysis.symbols import FunctionSymbol
from stubpy.config import StubConfig
from stubpy.core.context import StubContext
from stubpy.emit import generate_function_stub
from tests.conftest import (
    assert_valid_syntax,
    flatten,
    make_stub,
)


def _function_sym(
    name: str,
    live_func=None,
    is_async: bool = False,
    raw_return: "str | None" = None,
    raw_args: "dict[str, str] | None" = None,
    lineno: int = 1,
) -> "FunctionSymbol":
    from stubpy.analysis.harvest import FunctionInfo
    fi = FunctionInfo(
        name=name, lineno=lineno, is_async=is_async,
        raw_return_annotation=raw_return, raw_arg_annotations=raw_args or {},
    )
    return FunctionSymbol(name=name, lineno=lineno, live_func=live_func, ast_info=fi)


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
            "from typing import ClassVar\n"
            "class Foo:\n"
            "    x: ClassVar[int] = 0\n"
        )
        assert "from typing import ClassVar" in c

    def test_typing_imports_optional_in_legacy_style(self):
        """With union_style='legacy', Optional[str] appears in stub → Optional imported."""
        import tempfile
        from pathlib import Path

        from stubpy import generate_stub
        from stubpy.core.context import StubContext

        src = "from typing import Optional\ndef fn(x: Optional[str] = None) -> Optional[int]: ...\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext(config=StubConfig(union_style="legacy"))
        c = generate_stub(tmp, Path(tmp).with_suffix(".pyi").as_posix(), ctx=ctx)
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
