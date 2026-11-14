"""End-to-end generic bases, overloads, separators and union style."""
from __future__ import annotations

import tempfile
import textwrap

from stubpy.core.pipeline import render_module
from tests.conftest import assert_valid_syntax, make_stub


class TestGenericBases:
    """Generic subscript syntax is preserved in class definitions."""

    def test_generic_single_param(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Stack(Generic[T]):\n"
            "    def push(self, item: T) -> None: ...\n"
            "    def pop(self) -> T: ...\n"
        )
        assert "Generic[T]" in c
        assert "~" not in c
        assert_valid_syntax(c)

    def test_generic_multi_param(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "K = TypeVar('K')\n"
            "V = TypeVar('V')\n"
            "class Pair(Generic[K, V]):\n"
            "    pass\n"
        )
        assert "Generic[K, V]" in c
        assert_valid_syntax(c)

    def test_concrete_and_generic_bases(self):
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Base:\n"
            "    pass\n"
            "class Child(Base, Generic[T]):\n"
            "    pass\n"
        )
        assert "Base" in c
        assert "Generic[T]" in c
        assert_valid_syntax(c)

    def test_typevar_names_no_tilde(self):
        """TypeVar objects must render as bare names, never ~Name."""
        c = make_stub(
            "from typing import TypeVar, Generic\n"
            "T = TypeVar('T')\n"
            "class Container(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
        )
        assert "~" not in c


class TestOverloadStubs:
    """@overload variants are emitted; the implementation stub is suppressed."""

    def test_two_overloads_emitted(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def parse(x: int) -> int: ...\n"
            "@overload\n"
            "def parse(x: str) -> str: ...\n"
            "def parse(x):\n"
            "    return x\n"
        )
        assert c.count("@overload") == 2
        assert_valid_syntax(c)

    def test_overload_decorator_present(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert "@overload" in c
        assert_valid_syntax(c)

    def test_implementation_suppressed(self):
        """The bare (non-@overload) implementation must NOT appear in the stub."""
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def greet(name: str) -> str: ...\n"
            "@overload\n"
            "def greet(name: bytes) -> bytes: ...\n"
            "def greet(name):\n"
            "    return name\n"
        )
        assert c.count("def greet") == 2

    def test_three_overloads(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def process(x: int) -> int: ...\n"
            "@overload\n"
            "def process(x: str) -> str: ...\n"
            "@overload\n"
            "def process(x: bytes) -> bytes: ...\n"
            "def process(x):\n"
            "    return x\n"
        )
        assert c.count("@overload") == 3
        assert c.count("def process") == 3
        assert_valid_syntax(c)

    def test_overload_typing_import_added(self):
        c = make_stub(
            "from typing import overload\n"
            "@overload\n"
            "def f(x: int) -> int: ...\n"
            "@overload\n"
            "def f(x: str) -> str: ...\n"
            "def f(x): return x\n"
        )
        assert "overload" in c


class TestPositionalOnlySeparator:
    """The / separator is correctly emitted for positional-only parameters."""

    def test_slash_in_stub(self):
        c = make_stub(
            "def move(x: float, y: float, /, z: float = 0.0) -> None:\n"
            "    pass\n"
        )
        assert "/" in c
        assert_valid_syntax(c)

    def test_slash_before_regular_param(self):
        c = make_stub(
            "def fn(a: int, b: int, /, c: int) -> int:\n"
            "    return a + b + c\n"
        )
        assert "/" in c
        assert_valid_syntax(c)
        assert c.index("/") < c.index("c")

    def test_slash_and_star_in_same_function(self):
        c = make_stub(
            "def fn(a: int, /, b: int, *, c: int) -> int:\n"
            "    return a + b + c\n"
        )
        assert "/" in c
        assert "*" in c
        assert_valid_syntax(c)

    def test_method_with_pos_only(self):
        c = make_stub(
            "class MyClass:\n"
            "    def method(self, x: int, /, y: int = 0) -> int:\n"
            "        return x + y\n"
        )
        assert "/" in c
        assert_valid_syntax(c)

    def test_pos_only_kwargs_backtracing_valid_syntax(self):
        """Pos-only params absorbed via **kwargs produce valid stub syntax."""
        c = make_stub(
            "class Parent:\n"
            "    def __init__(self, x: int, y: int, /) -> None: pass\n"
            "class Child(Parent):\n"
            "    def __init__(self, **kwargs) -> None: pass\n"
        )
        assert_valid_syntax(c)


class TestTypingStyle:
    """Config.union_style controls Optional vs X | None output."""

    def test_modern_style_is_default(self):
        """Default mode emits 'str | None', not 'Optional[str]'."""
        c = make_stub(
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )
        assert "str | None" in c

    def test_legacy_style_emits_optional(self):
        """Legacy style emits 'Optional[str]' from typing."""
        from stubpy.config import Config
        from stubpy.core.context import StubContext
        source = (
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(textwrap.dedent(source))
            tmp = fh.name
        ctx = StubContext(config=Config(union_style="legacy"))
        c = render_module(tmp, ctx)
        assert "Optional[str]" in c
        assert "from typing import Optional" in c

    def test_modern_style_no_optional_import(self):
        """Modern style doesn't add 'Optional' to the typing import."""
        c = make_stub(
            "class A:\n"
            "    def f(self, x: str | None = None) -> None: pass\n"
        )
        assert "Optional" not in c
