"""Deprecated ``typing`` aliases are written in their modern forms."""
import textwrap

from stubpy.emit.modern import modernize
from tests.conftest import make_stub_ctx


class TestModernize:
    def test_renames_and_prefixes(self):
        text = "def f(a: List[Dict[str, typing.Tuple[int]]], cm: ContextManager[str]) -> typing.Callable[[], None]: ..."
        assert modernize(text) == (
            "def f(a: list[dict[str, tuple[int]]], cm: AbstractContextManager[str]) -> Callable[[], None]: ..."
        )

    def test_strings_attributes_and_local_names_untouched(self):
        text = "class List: ...\ndef f(a: List, b: 'Dict', c: mod.Dict) -> other.Type: ...\n"
        assert modernize(text) == text

    def test_names_imported_from_elsewhere_untouched(self):
        text = "def f(a: Dict) -> Iterator: ..."
        assert modernize(text, {"Dict": "from mylib import Dict"}) == "def f(a: Dict) -> Iterator: ..."


def test_stub_uses_modern_forms():
    """Python 3.13+ evaluates ``ContextManager[str]`` with its default exit type, ``bool | None``."""
    stub, _ = make_stub_ctx("""
        import typing
        from contextlib import contextmanager
        from typing import AsyncContextManager, Callable, ContextManager, Dict, Iterator, List, Optional, Pattern

        def run(cb: Callable[[int], None], items: List[Dict[str, int]]) -> Iterator[int]: ...
        def ctx(x: typing.Tuple[int, ...]) -> ContextManager[str]: ...
        def actx() -> AsyncContextManager[None]: ...
        def pat(p: Pattern[str], kind: typing.Type[int]) -> Optional[typing.FrozenSet[str]]: ...
        @contextmanager
        def opened(path: str) -> Iterator[str]:
            yield path
    """)
    stub = stub.replace(", bool | None]", "]")
    assert stub == textwrap.dedent("""\
        from collections.abc import Callable, Iterator
        from contextlib import AbstractAsyncContextManager, AbstractContextManager, contextmanager
        from re import Pattern

        def run(cb: Callable[[int], None], items: list[dict[str, int]]) -> Iterator[int]: ...

        def ctx(x: tuple[int, ...]) -> AbstractContextManager[str]: ...

        def actx() -> AbstractAsyncContextManager[None]: ...

        def pat(p: Pattern[str], kind: type[int]) -> frozenset[str] | None: ...

        @contextmanager
        def opened(path: str) -> Iterator[str]: ...
    """)
