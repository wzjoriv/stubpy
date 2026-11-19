"""Tests for async and abstract method stubs."""
from __future__ import annotations

import abc

from stubpy.core.context import StubContext
from stubpy.emit import generate_method_stub
from stubpy.emit._descriptors import is_abstract_method, is_async_callable, is_async_generator
from tests.conftest import (
    assert_valid_syntax,
    make_stub,
)


class TestAsyncDetection:

    def test_regular_async_fn(self):
        async def fetch():
            pass
        assert is_async_callable(fetch)

    def test_sync_fn_not_async(self):
        def sync():
            pass
        assert not is_async_callable(sync)

    def test_async_classmethod(self):
        class Foo:
            @classmethod
            async def cls_fetch(cls):
                pass
        assert is_async_callable(Foo.__dict__["cls_fetch"])

    def test_async_staticmethod(self):
        class Foo:
            @staticmethod
            async def static_fetch():
                pass
        assert is_async_callable(Foo.__dict__["static_fetch"])

    def test_async_generator_is_not_a_coroutine(self):
        async def agen():
            yield 1
        assert not is_async_callable(agen)
        assert is_async_generator(agen)

    def test_property_not_async_by_default(self):
        class Foo:
            @property
            def value(self):
                return 1
        assert not is_async_callable(Foo.__dict__["value"])


class TestAsyncMethodStubUnit:

    def test_async_method_emits_async_def(self):
        class Fetcher:
            async def fetch(self, url: str) -> bytes:
                return b""
        stub = generate_method_stub(Fetcher, "fetch", StubContext())
        assert "async def fetch" in stub
        assert "url: str" in stub
        assert "-> bytes" in stub

    def test_sync_method_no_async_prefix(self):
        class Foo:
            def compute(self, x: int) -> int:
                return x
        stub = generate_method_stub(Foo, "compute", StubContext())
        assert "async" not in stub
        assert "def compute" in stub

    def test_async_classmethod(self):
        class Repo:
            @classmethod
            async def load(cls, id: int) -> "Repo": ...
        stub = generate_method_stub(Repo, "load", StubContext())
        assert "@classmethod" in stub
        assert "async def load" in stub

    def test_async_staticmethod(self):
        class Utils:
            @staticmethod
            async def ping(host: str) -> bool: ...
        stub = generate_method_stub(Utils, "ping", StubContext())
        assert "@staticmethod" in stub
        assert "async def ping" in stub

    def test_async_generator_method(self):
        class Stream:
            async def chunks(self, size: int):
                yield b""
        stub = generate_method_stub(Stream, "chunks", StubContext())
        assert stub == "    def chunks(self, size: int) -> AsyncIterator[Any]: ..."


class TestAsyncMethodsIntegration:

    def test_async_method_in_output(self):
        c = make_stub(
            "class API:\n"
            "    async def get(self, url: str) -> bytes: ...\n"
            "    def post(self, url: str) -> None: ...\n"
        )
        assert "async def get" in c
        assert "def post" in c
        assert "async def post" not in c
        assert_valid_syntax(c)

    def test_async_classmethod_in_output(self):
        c = make_stub(
            "class DB:\n"
            "    @classmethod\n"
            "    async def connect(cls, dsn: str) -> 'DB': ...\n"
        )
        assert "@classmethod" in c
        assert "async def connect" in c

    def test_mixed_sync_async_class(self):
        c = make_stub(
            "class Worker:\n"
            "    def setup(self) -> None: ...\n"
            "    async def run(self) -> None: ...\n"
            "    def teardown(self) -> None: ...\n"
        )
        assert_valid_syntax(c)
        assert "async def run" in c
        assert "async def setup" not in c
        assert "async def teardown" not in c

    def test_async_return_annotation(self):
        c = make_stub(
            "from typing import Optional\n"
            "class Client:\n"
            "    async def fetch(self, url: str) -> Optional[str]: ...\n"
        )
        assert "async def fetch" in c
        assert ("str | None" in c or "Optional[str]" in c)

    def test_async_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "class Service:\n"
            "    async def process(self, a: int, b: str, c: float) -> None: ...\n"
        ))


class TestAbstractMethodDetection:

    def test_abstract_regular(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def must_impl(self):
                pass
        assert is_abstract_method(Foo.__dict__["must_impl"])

    def test_concrete_not_abstract(self):
        class Foo:
            def concrete(self):
                pass
        assert not is_abstract_method(Foo.__dict__["concrete"])

    def test_abstract_classmethod(self):
        class Foo(abc.ABC):
            @classmethod
            @abc.abstractmethod
            def cls_method(cls):
                pass
        assert is_abstract_method(Foo.__dict__["cls_method"])

    def test_abstract_staticmethod(self):
        class Foo(abc.ABC):
            @staticmethod
            @abc.abstractmethod
            def static_method():
                pass
        assert is_abstract_method(Foo.__dict__["static_method"])

    def test_abstract_property(self):
        class Foo(abc.ABC):
            @property
            @abc.abstractmethod
            def value(self) -> int: ...
        assert is_abstract_method(Foo.__dict__["value"])


class TestAbstractMethodStubUnit:

    def test_abstractmethod_decorator_emitted(self):
        class Shape(abc.ABC):
            @abc.abstractmethod
            def area(self) -> float: ...
        stub = generate_method_stub(Shape, "area", StubContext())
        assert "@abstractmethod" in stub
        assert "def area" in stub

    def test_classmethod_before_abstractmethod(self):
        class Base(abc.ABC):
            @classmethod
            @abc.abstractmethod
            def create(cls) -> "Base": ...
        stub = generate_method_stub(Base, "create", StubContext())
        assert "@classmethod" in stub
        assert "@abstractmethod" in stub
        assert stub.index("@classmethod") < stub.index("@abstractmethod")

    def test_staticmethod_before_abstractmethod(self):
        class Base(abc.ABC):
            @staticmethod
            @abc.abstractmethod
            def compute() -> int: ...
        stub = generate_method_stub(Base, "compute", StubContext())
        assert stub.index("@staticmethod") < stub.index("@abstractmethod")

    def test_abstract_property_decorator_order(self):
        class Shape(abc.ABC):
            @property
            @abc.abstractmethod
            def area(self) -> float: ...
        stub = generate_method_stub(Shape, "area", StubContext())
        assert "@abstractmethod" in stub
        assert "@property" in stub
        assert stub.index("@property") < stub.index("@abstractmethod")

    def test_concrete_no_abstractmethod(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def abstract_fn(self) -> None: ...

            def concrete_fn(self) -> None:  # noqa: B027  (deliberately concrete)
                pass
        assert "@abstractmethod" in generate_method_stub(Foo, "abstract_fn", StubContext())
        assert "@abstractmethod" not in generate_method_stub(Foo, "concrete_fn", StubContext())


class TestABCIntegration:

    def test_abc_base_in_stub(self):
        c = make_stub(
            "import abc\n"
            "class Shape(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def area(self) -> float: ...\n"
        )
        assert "class Shape(ABC):" in c
        assert "@abstractmethod" in c

    def test_abc_import_in_header(self):
        c = make_stub(
            "import abc\n"
            "class Base(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def method(self) -> None: ...\n"
        )
        assert "from abc import" in c
        assert "abstractmethod" in c
        assert "ABC" in c

    def test_abstract_classmethod_in_output(self):
        c = make_stub(
            "import abc\n"
            "class Factory(abc.ABC):\n"
            "    @classmethod\n"
            "    @abc.abstractmethod\n"
            "    def create(cls) -> 'Factory': ...\n"
        )
        assert "@classmethod" in c
        assert "@abstractmethod" in c
        assert_valid_syntax(c)

    def test_mixed_abstract_concrete(self):
        c = make_stub(
            "import abc\n"
            "class Widget(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def draw(self) -> None: ...\n"
            "    def hide(self) -> None: pass\n"
        )
        assert_valid_syntax(c)
        draw_idx = c.index("def draw")
        hide_idx = c.index("def hide")
        abstract_idx = c.index("@abstractmethod")
        assert abstract_idx < draw_idx
        assert "@abstractmethod" not in c[hide_idx:]

    def test_async_abstract_method(self):
        c = make_stub(
            "import abc\n"
            "class Source(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def read(self) -> bytes: ...\n"
        )
        assert "@abstractmethod" in c
        assert "async def read" in c
        assert_valid_syntax(c)

    def test_abc_class_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "import abc\n"
            "class Renderer(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def render(self, ctx: dict) -> str: ...\n"
            "    @classmethod\n"
            "    @abc.abstractmethod\n"
            "    def from_config(cls, cfg: dict) -> 'Renderer': ...\n"
            "    def reset(self) -> None: pass\n"
        ))
