"""End-to-end __all__ filtering, private names and source order."""
from __future__ import annotations

import textwrap
import types as _t

from stubpy.analysis.harvest import ast_harvest
from stubpy.analysis.symbols import build_symbol_table
from stubpy.config import Config
from stubpy.core.context import StubContext
from stubpy.core.pipeline import render_module
from tests.conftest import (
    assert_valid_syntax,
    make_stub,
)


def _make_stub_cfg(source: str, **cfg_kwargs) -> str:
    """Generate a stub from *source* text using optional :class:`Config` overrides."""
    import tempfile
    from pathlib import Path

    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        ctx_obj = StubContext(config=Config(**cfg_kwargs)) if cfg_kwargs else None
        return render_module(str(tmp), ctx_obj)
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_suffix(".pyi").unlink(missing_ok=True)


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


class TestIncludePrivate:

    def test_private_variables_included(self):
        c = _make_stub_cfg(
            "_SECRET: int = 1\nPUBLIC: str = 'x'\n",
            include_private=True,
        )
        assert "_SECRET: int" in c
        assert "PUBLIC: str" in c

    def test_private_functions_included(self):
        c = _make_stub_cfg(
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
        src = "__all__ = ['PUB']\nPUB: int = 1\nOTHER: int = 2\n_PRIV: str = 'x'\n"
        syms = ast_harvest(src)
        m = _t.ModuleType("_stubpy_target_allpriv")
        m.PUB, m.OTHER, m._PRIV = 1, 2, "x"

        tbl = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                 all_exports={"PUB"})
        assert "PUB" in tbl
        assert "OTHER" not in tbl
        assert "_PRIV" not in tbl

        tbl_p = build_symbol_table(m, "_stubpy_target_allpriv", syms,
                                   all_exports={"PUB"}, include_private=True)
        assert "PUB" in tbl_p
        assert "_PRIV" in tbl_p
        assert "OTHER" not in tbl_p

    def test_include_private_bypasses_all_for_private_names(self):
        c = _make_stub_cfg(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=True,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE: str" in c

    def test_include_private_false_still_hides_private_with_all(self):
        c = _make_stub_cfg(
            "__all__ = ['PUBLIC']\n"
            "PUBLIC: int = 1\n"
            "_PRIVATE: str = 'x'\n",
            include_private=False,
        )
        assert "PUBLIC: int" in c
        assert "_PRIVATE" not in c

    def test_respect_all_false(self):
        c = _make_stub_cfg(
            "__all__ = ['Alpha']\n"
            "class Alpha:\n    pass\n"
            "class Beta:\n    pass\n",
            respect_all=False,
        )
        assert "class Alpha:" in c
        assert "class Beta:" in c


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

    def test_unannotated_var_infers_and_records_info(self):
        """An unannotated variable with a literal value gets type inferred (INFO level)."""
        import tempfile

        src = "UNTYPED = 42\n"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(src)
            tmp = f.name
        ctx = StubContext()
        render_module(tmp, ctx)
        assert not ctx.diagnostics.has_warnings(), (
            "Successful literal inference should be INFO, not WARNING. "
            f"Got: {ctx.diagnostics.warnings}"
        )
        infos = ctx.diagnostics.info_items
        assert any("UNTYPED" in d.symbol or "Inferred" in d.message for d in infos)

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
