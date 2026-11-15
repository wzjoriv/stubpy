"""Stub quality: decorators, dunders, special classes, defaults, docstring types and diagnostics."""
from __future__ import annotations

import sys

import pytest

from stubpy.core.diagnostics import Stage
from tests.conftest import make_stub_ctx

MODES = ["runtime", "ast"]


@pytest.mark.parametrize("mode", MODES)
def test_context_managers_and_singledispatch_keep_their_decorators(mode):
    stub, _ = make_stub_ctx("""
        from contextlib import asynccontextmanager, contextmanager
        from functools import singledispatch
        from typing import AsyncIterator, Iterator
        class Doc:
            @classmethod
            @contextmanager
            def writing(cls, path: str) -> Iterator["Doc"]:
                yield cls()
            @asynccontextmanager
            async def session(self) -> AsyncIterator[int]:
                yield 1
        @singledispatch
        def render(value: object) -> str:
            return str(value)
        @render.register(int)
        def _render_int(value: int) -> str:
            return str(value)
    """, mode)
    assert "@classmethod\n    @contextmanager\n    def writing(cls, path: str) -> Iterator[Doc]: ..." in stub
    assert "@asynccontextmanager\n    def session(self) -> AsyncIterator[int]: ..." in stub
    assert "@singledispatch\ndef render(value: object) -> str: ..." in stub
    assert "_render_int" not in stub


@pytest.mark.parametrize("mode", MODES)
def test_async_generator_is_a_plain_def(mode):
    stub, _ = make_stub_ctx("""
        async def chunks(n: int):
            yield b""
        async def fetch() -> int:
            return 1
    """, mode)
    assert "def chunks(n: int) -> AsyncIterator[Any]: ..." in stub
    assert "async def chunks" not in stub
    assert "async def fetch() -> int: ..." in stub


@pytest.mark.parametrize("mode", MODES)
def test_descriptor_protocol_init_subclass_and_receiver_annotations(mode):
    stub, _ = make_stub_ctx("""
        from typing import Any, Generic, TypeVar
        T = TypeVar("T")
        E = TypeVar("E", bound="Base")
        class Field(Generic[T]):
            def __set_name__(self, owner: type, name: str) -> None: ...
            def __get__(self, obj: object, owner: type | None = None) -> T: ...
            def __set__(self, obj: object, value: T) -> None: ...
        class Base:
            def __init_subclass__(cls, *, tag: str = "", **kwargs: Any) -> None: ...
            def copy(self: E) -> E: ...
            @classmethod
            def make(cls: type[E]) -> E: ...
    """, mode)
    for method in ("__set_name__", "__get__", "__set__"):
        assert f"def {method}(self" in stub
    assert "    def __init_subclass__(\n        cls,\n        *,\n        tag: str = ''," in stub
    assert "@classmethod\n    def __init_subclass__" not in stub
    assert "def copy(self: E) -> E: ..." in stub
    assert "def make(cls: type[E]) -> E: ..." in stub


def test_partial_attribute_becomes_a_def():
    stub, _ = make_stub_ctx("""
        from functools import partial
        class Length:
            def __init__(self, value: float, unit: str = "") -> None: ...
        def line(x1: float, y1: float, *, stroke: str = "black", width: float = 1.0) -> Length: ...
        px = partial(Length, unit="px")
        dashed = partial(line, 0.0, stroke="red")
    """)
    assert "def px(\n    value: float,\n    *,\n    unit: str = 'px',\n) -> Length: ..." in stub
    assert "def dashed(\n    y1: float,\n    *,\n    stroke: str = 'red',\n    width: float = 1.0,\n) -> Length: ..." in stub
    assert "partial" not in stub.split("\n\n", 1)[1]


def test_partial_attribute_in_ast_mode():
    stub, _ = make_stub_ctx("""
        from functools import partial
        class Length: ...
        px = partial(Length, unit="px")
    """, "ast")
    assert "px: partial[Length]" in stub and "from functools import partial" in stub


def test_newtype_and_initvar_forwarding():
    stub, _ = make_stub_ctx("""
        from dataclasses import InitVar, dataclass
        from typing import Any, NewType
        UserId = NewType("UserId", str)
        @dataclass
        class Options:
            pretty: InitVar[bool] = True
            indent: str = "  "
            def __post_init__(self, pretty: bool) -> None: ...
        class Writer:
            def __init__(self, **kwargs: Any) -> None:
                self.options = Options(**kwargs)
            def owner(self) -> UserId: ...
    """)
    assert "pretty: InitVar[bool] = True" in stub and "indent: str = '  '" in stub
    writer = stub.split("class Writer")[1]
    assert "pretty: bool = True," in writer and "InitVar" not in writer
    assert "def owner(self) -> UserId: ..." in writer


def test_dataclass_and_namedtuple_drop_synthesized_members():
    stub, _ = make_stub_ctx("""
        from dataclasses import dataclass, field
        from typing import NamedTuple, Protocol
        @dataclass
        class P:
            x: int = 0
            tags: list[str] = field(default_factory=list)
        class Pair(NamedTuple):
            a: int
            b: int = 1
        class Sink(Protocol):
            def write(self, text: str) -> None: ...
    """)
    assert "x: int = 0" in stub and "tags: list[str] = ..." in stub
    assert "__hash__" not in stub
    assert "__repr__" not in stub
    assert "def __init__(self, *args" not in stub


@pytest.mark.parametrize("mode", MODES)
def test_popped_and_deleted_kwargs_take_the_callee_type(mode):
    stub, _ = make_stub_ctx("""
        from typing import Any
        def connect(host: str, *, ssl: bool = False, timeout: float = 1.0, b: int = 2) -> None: ...
        def open_url(url: str, **kwargs: Any) -> None:
            verbose = kwargs.pop("verbose", None)
            del kwargs["b"]
            connect(url, **kwargs)
    """, mode)
    if mode == "runtime":
        assert "b: int = 2," in stub
        assert "verbose=None," in stub
        assert "ellipsis" not in stub
    assert "verbose = None" not in stub


def test_setdefault_keys_stay_available():
    stub, _ = make_stub_ctx("""
        from typing import Any
        def make(*, x: str = "0", y: str = "0") -> None: ...
        def shadow(**kwargs: Any) -> None:
            kwargs.setdefault("x", "-20%")
            make(**kwargs)
    """)
    shadow = stub.split("def shadow")[1]
    assert "x: str = '0'" in shadow and "y: str = '0'" in shadow


@pytest.mark.parametrize("mode", MODES)
def test_enum_aliases_survive(mode):
    stub, _ = make_stub_ctx("""
        import enum
        class Unit(str, enum.Enum):
            NONE = ""
            PX = "px"
            USER = ""
        class Kind(enum.Enum):
            A = enum.auto()
            GROUP = A
    """, mode)
    assert "USER = NONE" in stub and "GROUP = A" in stub


def test_docstring_types_become_annotations_and_comments_never_swallow_code():
    stub, _ = make_stub_ctx('''
        def area(w, h, extra=None):
            """Area.

            Parameters
            ----------
            w : float
                Width.
            h : array-like
                Height.
            extra : int, optional

            Returns
            -------
            float
            """
    ''', infer_types=True, include_docstrings=True)
    assert "    w: float,\n    h,  # type: array-like\n    extra: int | None = None,\n) -> float:" in stub
    assert '    """Area.\n\n    Parameters\n    ----------\n    w : float\n        Width.' in stub


@pytest.mark.parametrize("style, expected", [
    ("modern", "def f(self, a: int | str, b: Length | None = None) -> int | None: ..."),
    ("legacy", "def f(self, a: Union[int, str], b: Optional[Length] = None) -> Optional[int]: ..."),
])
@pytest.mark.parametrize("mode", MODES)
def test_union_style_applies_in_both_modes(mode, style, expected):
    stub, _ = make_stub_ctx("""
        from typing import Optional, Union
        Length = Union[str, float]
        class C:
            def f(self, a: Union[int, str], b: Optional[Length] = None) -> Optional[int]: ...
    """, mode, union_style=style)
    assert expected in stub


@pytest.mark.parametrize("verbose, level", [(False, "INFO"), (True, "WARNING")])
def test_unresolved_kwargs_are_reported(verbose, level):
    stub, ctx = make_stub_ctx("""
        from typing import Any
        from json import dumps as helper
        def f(a: int, **kw: Any) -> str:
            return helper(a, **kw)
    """, verbose=verbose)
    notes = [d for d in ctx.diagnostics if d.stage is Stage.RESOLVE and "helper" in d.message]
    assert notes and notes[0].level.name == level


def test_class_without_own_orig_bases_keeps_its_real_base():
    stub, _ = make_stub_ctx("""
        from typing import Generic, TypeVar
        T = TypeVar("T")
        class Box(Generic[T]): ...
        class _IntBox(Box[int]): ...
        class Leaf(_IntBox): ...
    """)
    assert "class Leaf(_IntBox):" in stub


@pytest.mark.parametrize("mode", MODES)
def test_c_types_and_lowercase_attribute_types_are_importable(mode):
    stub, _ = make_stub_ctx("""
        import functools
        import types as _t
        OVERLOAD = "overload"
        def load(module: _t.ModuleType, fn: functools.partial) -> None: ...
    """, mode)
    if mode == "runtime":
        assert "def load(module: types.ModuleType, fn: partial) -> None: ..." in stub
        assert "import types\nfrom functools import partial" in stub
    else:
        assert "import functools\nimport types as _t" in stub
    assert "overload" not in stub.split("\n\n")[0]


def test_ast_infers_instances_of_local_classes():
    stub, _ = make_stub_ctx("""
        class Factory: ...
        next_id = Factory()
    """, "ast")
    assert "next_id: Factory" in stub


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 syntax needs Python 3.12+")
@pytest.mark.parametrize("mode", MODES)
def test_pep695_type_parameters(mode):
    stub, _ = make_stub_ctx("""
        from collections.abc import Iterable
        type Pair[T] = tuple[T, T]
        class Stack[T]:
            def push(self, item: T) -> T: ...
        def first[T](items: Iterable[T]) -> T: ...
    """, mode)
    assert "type Pair[T] = tuple[T, T]" in stub
    assert "class Stack[T]:" in stub and "Generic" not in stub
    assert "def first[T](items: Iterable[T]) -> T: ..." in stub
