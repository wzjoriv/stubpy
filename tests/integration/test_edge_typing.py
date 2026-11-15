"""Edge cases: annotations and typing constructs."""
from __future__ import annotations

import sys
import typing

import pytest

from tests.conftest import flatten, make_stub_ctx

MODES = ["runtime", "ast"]


class TestLazyAnnotations:
    def test_forward_references_in_dataclass_and_typeddict(self):
        stub, _ = make_stub_ctx("""
            from __future__ import annotations
            from dataclasses import dataclass
            from typing import TypedDict
            @dataclass
            class A:
                b: B | None = None
            class B:
                a: A
            class TD(TypedDict):
                a: A
                n: int
        """)
        assert "b: B | None" in stub
        assert "a: A" in stub
        assert "n: int" in stub

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 649 lazy annotations need Python 3.14")
    def test_lazy_annotations_without_future_import(self):
        stub, _ = make_stub_ctx("""
            from dataclasses import dataclass
            from typing import TypedDict
            @dataclass
            class A:
                b: B | None = None
            class B:
                a: A
            class TD(TypedDict):
                a: A
        """)
        assert "b: B | None" in stub
        assert "class TD(TypedDict)" in stub


@pytest.mark.parametrize("mode", MODES)
class TestTypingConstructs:
    def test_type_checking_import_is_imported_in_stub(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from decimal import Decimal
            def f(x: "Decimal") -> "Decimal": ...
        """, mode)
        assert "from decimal import Decimal" in stub
        assert "Decimal" in stub.split("def f")[1]

    def test_annotated_with_unimportable_metadata(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import Annotated
            class _Meta:
                def __init__(self, n): self.n = n
            def f(x: Annotated[int, _Meta(3)]) -> None: ...
        """, mode)
        assert "def f(x:" in stub

    def test_recursive_alias_does_not_recurse_forever(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import Union
            Json = Union[dict[str, "Json"], list["Json"], str, int, None]
            def load(text: str) -> Json: ...
        """, mode)
        assert "def load" in stub

    def test_paramspec_and_concatenate_are_preserved(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import Callable, Concatenate, ParamSpec, TypeVar
            P = ParamSpec("P")
            R = TypeVar("R")
            def deco(f: Callable[P, R]) -> Callable[P, R]: ...
            def pre(f: Callable[Concatenate[int, P], R]) -> Callable[P, R]: ...
            def anyargs(f: Callable[..., int]) -> None: ...
        """, mode)
        flat = flatten(stub)
        assert "Callable[P, R]" in flat
        assert "Callable[Concatenate[int, P], R]" in flat
        assert "Callable[..., int]" in flat
        assert "Callable[[P]" not in flat and "[...]" not in flat
        assert 'P = ParamSpec("P")' in stub or "P = ParamSpec('P')" in stub

    def test_self_and_noreturn_are_preserved(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import NoReturn
            from typing_extensions import Self
            class Node:
                def copy(self) -> Self: ...
            def fail() -> NoReturn: ...
        """ if sys.version_info < (3, 11) and _has_typing_extensions() else """
            from typing import NoReturn, Self
            class Node:
                def copy(self) -> Self: ...
            def fail() -> NoReturn: ...
        """ if sys.version_info >= (3, 11) else """
            from typing import NoReturn
            def fail() -> NoReturn: ...
        """, mode)
        assert "-> NoReturn" in stub
        if sys.version_info >= (3, 11) or _has_typing_extensions():
            assert "def copy(self) -> Self" in stub

    @pytest.mark.skipif(not hasattr(typing, "TypeIs"), reason="typing.TypeIs needs Python 3.13")
    def test_typeis_is_preserved(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import TypeIs
            def is_str(x: object) -> TypeIs[str]: ...
        """, mode)
        assert "-> TypeIs[str]" in stub
        assert "TypeIs" in stub.splitlines()[0]

    def test_nested_optional_union_flattens(self, mode):
        stub, _ = make_stub_ctx("""
            from typing import Optional, Union
            def f(x: Union[int, Optional[str]]) -> None: ...
        """, mode)
        if mode == "runtime":
            assert "x: int | str | None" in stub
        assert "None | None" not in stub


@pytest.mark.skipif(sys.version_info < (3, 11), reason="star-unpacking in annotations needs Python 3.11")
@pytest.mark.parametrize("mode", MODES)
def test_typevartuple_unpack_is_preserved(mode):
    stub, _ = make_stub_ctx("""
        from typing import TypeVarTuple, Unpack
        Ts = TypeVarTuple("Ts")
        def tup(*args: Unpack[Ts]) -> tuple[Unpack[Ts]]: ...
    """, mode)
    assert "Ts = TypeVarTuple" in stub
    assert "*args: " in stub and "Ts" in stub.split("def tup")[1]


def _has_typing_extensions() -> bool:
    try:
        import typing_extensions  # noqa: F401
    except ImportError:
        return False
    return True
