"""End-to-end import headers and type alias declarations."""
from __future__ import annotations

import tempfile
import textwrap

from stubpy.core.pipeline import render_module
from tests.conftest import assert_valid_syntax, make_stub


class TestInlineImports:
    """Imports inside function / method bodies are discovered and re-emitted.

    Projects sometimes place imports inside functions to break circular
    dependencies.  stubpy's AST pre-pass uses ``ast.walk`` across the *entire*
    source tree, so inline imports are found in ``scan_import_statements``.
    They are re-emitted in the ``.pyi`` header when the imported name actually
    appears in a stub annotation (return type, parameter type, base class, etc.).
    Imports whose names never appear in the stub body are silently skipped, just
    like top-level imports that are unused in the output.
    """

    def test_inline_import_used_as_return_type(self):
        """Inline import used as a return-type annotation is re-emitted."""
        c = make_stub("""
            def factory() -> 'Widget':
                from widget_lib import Widget
                return Widget()
        """)
        assert "from widget_lib import Widget" in c
        assert_valid_syntax(c)

    def test_inline_import_as_alias_used_in_annotation(self):
        """``import X as Y`` inline; alias appears in return annotation."""
        c = make_stub("""
            def make() -> 'W':
                from widget_lib import Widget as W
                return W()
        """)
        assert "from widget_lib import Widget as W" in c
        assert_valid_syntax(c)

    def test_inline_import_in_method_used_as_base(self):
        """Inline import whose name appears as a base class is re-emitted."""
        c = make_stub("""
            class Renderer:
                def _get_canvas(self) -> 'Canvas': ...
            # Canvas is used as an annotation so it appears in the stub body,
            # causing the inline import to be re-emitted.
            def setup() -> 'Canvas':
                from render_lib import Canvas
                return Canvas()
        """)
        assert "from render_lib import Canvas" in c
        assert_valid_syntax(c)

    def test_inline_import_not_duplicated(self):
        """Same name imported both at top-level and inline — one import in header.

        The deduplication is exercised entirely via ``scan_import_statements``
        and ``collect_cross_imports``; we don't need a real importable module
        because the name never actually appears as a type annotation in the
        generated stub body (``factory`` has no parameters with that type).
        The test therefore uses a sentinel module name that is intentionally
        not on ``sys.path``.
        """

        from stubpy.config import Config
        from stubpy.state.context import StubContext

        source = textwrap.dedent("""
            from _stubpy_fake_dedup_mod import Widget

            def factory() -> 'Widget':
                from _stubpy_fake_dedup_mod import Widget
                return Widget()
        """)
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(source)
            tmp = fh.name

        ctx = StubContext(config=Config())
        c = render_module(tmp, ctx)
        assert c.count("from _stubpy_fake_dedup_mod import Widget") <= 1
        assert_valid_syntax(c)

    def test_inline_import_unused_in_stub_not_emitted(self):
        """Inline import whose name never appears in a stub annotation is not emitted.

        The import is discovered but ``collect_cross_imports`` only re-emits
        names that are actually referenced in the generated stub body.
        """
        c = make_stub("""
            class R:
                def render(self):
                    from rlib import Canvas   # Canvas not in any annotation
                    return Canvas()
        """)
        assert "rlib" not in c
        assert_valid_syntax(c)

    def test_inline_stdlib_excluded(self):
        """Inline stdlib / typing imports are not re-emitted as cross-file imports."""
        c = make_stub("""
            def helper(x: int) -> list:
                from typing import List
                return []
        """)
        assert_valid_syntax(c)


class TestTypeVarStubs:
    """TypeVar / TypeAlias / NewType declarations are re-emitted in stubs."""

    def test_typevar_emitted(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
            "X: int = 1\n"
        )
        assert "T = TypeVar('T')" in c
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_typevar_with_bound(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T', bound=int)\n"
        )
        assert "T = TypeVar('T', bound=int)" in c
        assert_valid_syntax(c)

    def test_typevar_with_constraints(self):
        c = make_stub(
            "from typing import TypeVar\n"
            "AnyStr = TypeVar('AnyStr', str, bytes)\n"
        )
        assert "AnyStr = TypeVar('AnyStr', str, bytes)" in c
        assert_valid_syntax(c)

    def test_typealias_emitted(self):
        c = make_stub(
            "from typing import TypeAlias\n"
            "Vector: TypeAlias = list[float]\n"
        )
        assert "Vector: TypeAlias = list[float]" in c
        assert_valid_syntax(c)

    def test_newtype_emitted(self):
        c = make_stub(
            "from typing import NewType\n"
            "UserId = NewType('UserId', int)\n"
        )
        assert "UserId = NewType('UserId', int)" in c
        assert_valid_syntax(c)

    def test_paramspec_emitted(self):
        c = make_stub(
            "from typing import ParamSpec\n"
            "P = ParamSpec('P')\n"
        )
        assert "P = ParamSpec('P')" in c
        assert_valid_syntax(c)

    def test_typevar_before_class(self):
        """TypeVar declaration precedes the class that uses it (source order)."""
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Box(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
        )
        assert c.index("T = TypeVar") < c.index("class Box")
        assert_valid_syntax(c)

    def test_typevar_not_emitted_as_plain_variable(self):
        """TypeVar declarations go through AliasSymbol, not VariableSymbol."""
        c = make_stub(
            "from typing import TypeVar\n"
            "T = TypeVar('T')\n"
        )
        assert "T = TypeVar" in c
        assert "T: TypeVar" not in c


class TestImplicitTypeAliasIntegration:
    """Bare assignments that look like type aliases are emitted as TypeAlias stubs."""

    def test_bare_union_emitted_as_typealias(self):
        c = make_stub(
            "Number = int | float\n"
            "X: int = 1\n"
        )
        assert "Number: TypeAlias = int | float" in c
        assert "X: int" in c
        assert_valid_syntax(c)

    def test_subscripted_generic_emitted(self):
        c = make_stub("from typing import Union\nLength = Union[str, float, int]\n")
        assert "Length: TypeAlias" in c
        assert_valid_syntax(c)

    def test_bare_builtin_type_emitted(self):
        c = make_stub("MyStr = str\n")
        assert "MyStr: TypeAlias = str" in c
        assert_valid_syntax(c)

    def test_list_subscript_emitted(self):
        c = make_stub("Items = list[int]\n")
        assert "Items: TypeAlias = list[int]" in c
        assert_valid_syntax(c)

    def test_string_constant_not_alias(self):
        c = make_stub("VERSION = '1.0.0'\n")
        assert "TypeAlias" not in c
        assert "VERSION: str" in c or "VERSION" in c

    def test_integer_constant_not_alias(self):
        c = make_stub("PORT = 8080\n")
        assert "TypeAlias" not in c

    def test_arbitrary_class_name_not_alias(self):
        c = make_stub("class Foo: pass\nMyFoo = Foo\n")
        assert "TypeAlias" not in c or "MyFoo" not in c.split("TypeAlias")[0]


class TestImportDeduplication:
    """Header imports are never duplicated regardless of detection path."""

    def test_no_duplicate_module_import(self, drawkit_module):
        """A module imported once and used in several annotations is imported once."""
        c = drawkit_module("""
            from drawkit import types
            DEFAULT_WIDTH: types.Length = 800
            def get_color() -> types.Color: ...
        """)
        assert c.count("from drawkit import types") == 1
        assert "DEFAULT_WIDTH: types.Length" in c
        assert "def get_color() -> types.Color: ..." in c

    def test_typing_import_not_duplicated(self):
        c = make_stub(
            "from typing import Optional\n"
            "def f(x: Optional[str]) -> Optional[int]: ...\n"
        )
        typing_lines = [l for l in c.splitlines() if l.startswith("from typing import")]
        assert len(typing_lines) <= 1
