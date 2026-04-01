"""
tests/test_special_classes.py
------------------------------
Tests for special-class and special-method stub generation:
  - Async methods (``async def``) on regular, classmethod, and staticmethod
  - Abstract methods (``@abstractmethod``) and ABC base classes
  - ``@dataclass`` classes — synthesised ``__init__``, field handling
  - NamedTuple subclasses — field annotations and defaults
  - ``collect_special_imports`` — header assembly for abc / dataclasses
  - Integration combining all special-class patterns
"""
from __future__ import annotations

import abc
import dataclasses as _dc
import typing


from tests.conftest import assert_valid_syntax, flatten, make_stub
from stubpy.context import StubContext
from stubpy.emitter import (
    _is_abstract_method,
    _is_async_callable,
    _is_dataclass,
    _is_namedtuple,
    generate_class_stub,
    generate_method_stub,
)
from stubpy.imports import collect_special_imports


# ============================================================================
# Async method detection
# ============================================================================

class TestAsyncDetection:

    def test_regular_async_fn(self):
        async def fetch():
            pass
        assert _is_async_callable(fetch)

    def test_sync_fn_not_async(self):
        def sync():
            pass
        assert not _is_async_callable(sync)

    def test_async_classmethod(self):
        class Foo:
            @classmethod
            async def cls_fetch(cls):
                pass
        assert _is_async_callable(Foo.__dict__["cls_fetch"])

    def test_async_staticmethod(self):
        class Foo:
            @staticmethod
            async def static_fetch():
                pass
        assert _is_async_callable(Foo.__dict__["static_fetch"])

    def test_async_generator(self):
        async def agen():
            yield 1
        assert _is_async_callable(agen)

    def test_property_not_async_by_default(self):
        class Foo:
            @property
            def value(self):
                return 1
        assert not _is_async_callable(Foo.__dict__["value"])


# ============================================================================
# Async method stubs — unit
# ============================================================================

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
        assert "async def chunks" in stub


# ============================================================================
# Async methods via generate_stub
# ============================================================================

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
        # Modern style: str | None; accept either form
        assert ("str | None" in c or "Optional[str]" in c)

    def test_async_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "class Service:\n"
            "    async def process(self, a: int, b: str, c: float) -> None: ...\n"
        ))


# ============================================================================
# abstractmethod detection
# ============================================================================

class TestAbstractMethodDetection:

    def test_abstract_regular(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def must_impl(self):
                pass
        assert _is_abstract_method(Foo.__dict__["must_impl"])

    def test_concrete_not_abstract(self):
        class Foo:
            def concrete(self):
                pass
        assert not _is_abstract_method(Foo.__dict__["concrete"])

    def test_abstract_classmethod(self):
        class Foo(abc.ABC):
            @classmethod
            @abc.abstractmethod
            def cls_method(cls):
                pass
        assert _is_abstract_method(Foo.__dict__["cls_method"])

    def test_abstract_staticmethod(self):
        class Foo(abc.ABC):
            @staticmethod
            @abc.abstractmethod
            def static_method():
                pass
        assert _is_abstract_method(Foo.__dict__["static_method"])

    def test_abstract_property(self):
        class Foo(abc.ABC):
            @property
            @abc.abstractmethod
            def value(self) -> int: ...
        assert _is_abstract_method(Foo.__dict__["value"])


# ============================================================================
# abstractmethod stubs — unit
# ============================================================================

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
        assert stub.index("@abstractmethod") < stub.index("@property")

    def test_concrete_no_abstractmethod(self):
        class Foo(abc.ABC):
            @abc.abstractmethod
            def abstract_fn(self) -> None: ...

            def concrete_fn(self) -> None:
                pass
        assert "@abstractmethod" in generate_method_stub(Foo, "abstract_fn", StubContext())
        assert "@abstractmethod" not in generate_method_stub(Foo, "concrete_fn", StubContext())


# ============================================================================
# ABC via generate_stub
# ============================================================================

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
        # @abstractmethod appears before draw, not before hide
        draw_idx = c.index("def draw")
        hide_idx = c.index("def hide")
        abstract_idx = c.index("@abstractmethod")
        assert abstract_idx < draw_idx
        # no @abstractmethod between hide and end
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


# ============================================================================
# dataclass detection
# ============================================================================

class TestDataclassDetection:

    def test_decorated_is_dataclass(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert _is_dataclass(Foo)

    def test_plain_class_not_dataclass(self):
        class Plain:
            x: int = 0
        assert not _is_dataclass(Plain)

    def test_dataclass_not_namedtuple(self):
        @_dc.dataclass
        class Foo:
            x: int
        assert not _is_namedtuple(Foo)


# ============================================================================
# dataclass stubs — unit
# ============================================================================

class TestDataclassStubUnit:

    def test_decorator_emitted(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert stub.splitlines()[0] == "@dataclass"
        assert "class Point:" in stub.splitlines()[1]

    def test_init_synthesised(self):
        @_dc.dataclass
        class Point:
            x: float
            y: float = 0.0
        stub = generate_class_stub(Point, StubContext())
        assert "def __init__" in stub
        assert "x: float" in stub
        assert "y: float = 0.0" in stub

    def test_default_factory(self):
        @_dc.dataclass
        class Bag:
            items: list = _dc.field(default_factory=list)
        stub = flatten(generate_class_stub(Bag, StubContext()))
        assert "items: list = ..." in stub

    def test_init_false_excluded_from_init(self):
        @_dc.dataclass
        class Config:
            name: str
            _computed: int = _dc.field(default=0, init=False)
        stub = flatten(generate_class_stub(Config, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "_computed" not in init_line

    def test_classvar_excluded_from_init(self):
        @_dc.dataclass
        class Model:
            MAX: typing.ClassVar[int] = 100
            value: int = 0
        stub = flatten(generate_class_stub(Model, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_annotations_in_body(self):
        @_dc.dataclass
        class Product:
            name: str
            price: float = 9.99
        stub = generate_class_stub(Product, StubContext())
        assert "name: str" in stub
        assert "price: float" in stub

    def test_post_init_included(self):
        @_dc.dataclass
        class Validated:
            x: int
            def __post_init__(self) -> None:
                assert self.x >= 0
        stub = generate_class_stub(Validated, StubContext())
        assert "__post_init__" in stub

    def test_inherited_fields_annotated(self):
        @_dc.dataclass
        class Base:
            x: int
        @_dc.dataclass
        class Child(Base):
            y: str
        stub = flatten(generate_class_stub(Child, StubContext()))
        init_line = [l for l in stub.splitlines() if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line


# ============================================================================
# dataclass via generate_stub
# ============================================================================

class TestDataclassIntegration:

    def test_basic_dataclass(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "def __init__" in c

    def test_dataclasses_import_in_header(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Foo:\n"
            "    x: int\n"
        )
        assert "from dataclasses import dataclass" in c

    def test_default_factory_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Bag:\n"
            "    items: list = field(default_factory=list)\n"
        )
        assert_valid_syntax(c)
        assert "items: list = ..." in flatten(c)

    def test_init_false_in_output(self):
        c = make_stub(
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Config:\n"
            "    name: str\n"
            "    counter: int = field(default=0, init=False)\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "name: str" in init_line
        assert "counter" not in init_line

    def test_classvar_not_in_init_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "from typing import ClassVar\n"
            "@dataclass\n"
            "class Model:\n"
            "    MAX: ClassVar[int] = 100\n"
            "    value: int = 0\n"
        )
        assert_valid_syntax(c)
        init_line = [l for l in flatten(c).splitlines() if "def __init__" in l][0]
        assert "value: int" in init_line
        assert "MAX" not in init_line

    def test_dataclass_inheritance_output(self):
        c = make_stub(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Base:\n"
            "    x: int\n"
            "@dataclass\n"
            "class Child(Base):\n"
            "    y: str\n"
        )
        assert_valid_syntax(c)
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "x: int" in init_line
        assert "y: str" in init_line

    def test_complex_dataclass_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from dataclasses import dataclass, field\n"
            "from typing import ClassVar, Optional\n"
            "@dataclass\n"
            "class Record:\n"
            "    MAX: ClassVar[int] = 1000\n"
            "    id: int\n"
            "    name: str = 'unnamed'\n"
            "    tags: list = field(default_factory=list)\n"
            "    _internal: bool = field(default=False, init=False)\n"
            "    def validate(self) -> bool: return True\n"
        ))


# ============================================================================
# NamedTuple detection
# ============================================================================

class TestNamedTupleDetection:

    def test_typed_namedtuple(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        assert _is_namedtuple(Point)

    def test_plain_class_not_namedtuple(self):
        class Foo:
            x: int
        assert not _is_namedtuple(Foo)

    def test_plain_tuple_subclass_not_namedtuple(self):
        class T(tuple):
            pass
        assert not _is_namedtuple(T)


# ============================================================================
# NamedTuple stubs — unit
# ============================================================================

class TestNamedTupleStubUnit:

    def test_class_line(self):
        class Color(typing.NamedTuple):
            r: int
            g: int
        assert generate_class_stub(Color, StubContext()).startswith("class Color(NamedTuple):")

    def test_field_annotations(self):
        class Point(typing.NamedTuple):
            x: float
            y: float
        stub = generate_class_stub(Point, StubContext())
        assert "x: float" in stub
        assert "y: float" in stub

    def test_default_values(self):
        class Color(typing.NamedTuple):
            r: int
            g: int = 0
            b: int = 0
        stub = generate_class_stub(Color, StubContext())
        assert "r: int" in stub
        assert "g: int = 0" in stub
        assert "b: int = 0" in stub

    def test_no_generated_methods(self):
        class Pair(typing.NamedTuple):
            a: str
            b: str
        stub = generate_class_stub(Pair, StubContext())
        assert "_make" not in stub
        assert "_asdict" not in stub
        assert "_replace" not in stub

    def test_uses_namedtuple_base_not_tuple(self):
        class Point(typing.NamedTuple):
            x: float
        stub = generate_class_stub(Point, StubContext())
        assert "class Point(NamedTuple):" in stub
        assert "class Point(tuple):" not in stub

    def test_empty_namedtuple(self):
        class Empty(typing.NamedTuple):
            pass
        stub = generate_class_stub(Empty, StubContext())
        assert "class Empty(NamedTuple):" in stub
        assert "..." in stub


# ============================================================================
# NamedTuple via generate_stub
# ============================================================================

class TestNamedTupleIntegration:

    def test_namedtuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "r: int" in c
        assert "g: int = 0" in c

    def test_namedtuple_import_in_header(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
        )
        assert "from typing import NamedTuple" in c

    def test_multiple_namedtuples(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
            "    y: float\n"
            "class RGB(NamedTuple):\n"
            "    r: int\n"
            "    g: int\n"
            "    b: int\n"
        )
        assert_valid_syntax(c)
        assert "class Point(NamedTuple):" in c
        assert "class RGB(NamedTuple):" in c

    def test_no_tuple_in_output(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Point(NamedTuple):\n"
            "    x: float\n"
        )
        assert "class Point(NamedTuple):" in c
        assert "tuple" not in c

    def test_namedtuple_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "from typing import NamedTuple\n"
            "class Vector(NamedTuple):\n"
            "    x: float = 0.0\n"
            "    y: float = 0.0\n"
            "    z: float = 0.0\n"
        ))

    def test_namedtuple_and_class_coexist(self):
        c = make_stub(
            "from typing import NamedTuple\n"
            "class Size(NamedTuple):\n"
            "    width: int\n"
            "    height: int\n"
            "class Canvas:\n"
            "    def __init__(self, size: 'Size') -> None: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Size(NamedTuple):" in c
        assert "class Canvas:" in c


# ============================================================================
# collect_special_imports
# ============================================================================

class TestCollectSpecialImports:

    def test_abstractmethod_only(self):
        result = collect_special_imports("@abstractmethod\ndef foo(): ...")
        assert "abc" in result
        assert "abstractmethod" in result["abc"]

    def test_abc_base_only(self):
        result = collect_special_imports("class Foo(ABC):\n    pass")
        assert "abc" in result
        assert "ABC" in result["abc"]

    def test_both_abc_names(self):
        result = collect_special_imports(
            "class Foo(ABC):\n    @abstractmethod\n    def bar(): ..."
        )
        assert "ABC" in result["abc"]
        assert "abstractmethod" in result["abc"]

    def test_dataclass(self):
        result = collect_special_imports("@dataclass\nclass Foo:\n    x: int")
        assert "dataclasses" in result
        assert "dataclass" in result["dataclasses"]

    def test_empty_body(self):
        result = collect_special_imports("class Foo:\n    def bar(self) -> int: ...")
        assert result == {}


# ============================================================================
# Integration — all special-class patterns combined
# ============================================================================

class TestSpecialClassIntegration:

    def test_all_patterns_combined(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "from typing import NamedTuple\n"
            "\n"
            "class Color(NamedTuple):\n"
            "    r: int\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: float\n"
            "    y: float = 0.0\n"
            "\n"
            "class Renderer(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def render(self, ctx: dict) -> str: ...\n"
        )
        assert_valid_syntax(c)
        assert "class Color(NamedTuple):" in c
        assert "@dataclass" in c
        assert "class Point:" in c
        assert "class Renderer(ABC):" in c
        assert "@abstractmethod" in c
        assert "async def render" in c

    def test_dataclass_with_abc_base(self):
        c = make_stub(
            "import abc\n"
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Entity(abc.ABC):\n"
            "    id: int\n"
            "    @abc.abstractmethod\n"
            "    def serialize(self) -> dict: ...\n"
        )
        assert_valid_syntax(c)
        assert "@dataclass" in c
        assert "class Entity(ABC):" in c
        assert "@abstractmethod" in c
        assert "def __init__" in c

    def test_kwargs_backtracing_unaffected(self):
        c = make_stub(
            "class Base:\n"
            "    def __init__(self, x: float, y: float = 0.0) -> None: pass\n"
            "class Child(Base):\n"
            "    def __init__(self, label: str, **kwargs) -> None:\n"
            "        super().__init__(**kwargs)\n"
        )
        child_section = c.split("class Child")[1]
        init_line = [l for l in flatten(child_section).splitlines()
                     if "def __init__" in l][0]
        assert "label: str" in init_line
        assert "x: float" in init_line
        assert "**kwargs" not in init_line

    def test_async_in_abc(self):
        c = make_stub(
            "import abc\n"
            "class Stream(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    async def read(self, n: int) -> bytes: ...\n"
            "    async def write(self, data: bytes) -> None: pass\n"
        )
        assert_valid_syntax(c)
        assert "@abstractmethod" in c
        assert c.count("async def") == 2

    def test_full_combination_valid_syntax(self):
        assert_valid_syntax(make_stub(
            "import abc\n"
            "from dataclasses import dataclass, field\n"
            "from typing import NamedTuple, Optional\n"
            "\n"
            "class RGB(NamedTuple):\n"
            "    r: int = 0\n"
            "    g: int = 0\n"
            "    b: int = 0\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
            "    tags: list = field(default_factory=list)\n"
            "\n"
            "class Protocol(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def connect(self, cfg: Config) -> None: ...\n"
            "    @abc.abstractmethod\n"
            "    async def send(self, data: bytes) -> int: ...\n"
            "    def close(self) -> None: pass\n"
        ))

    def test_graphics_demo_backward_compat(self):
        from pathlib import Path
        import tempfile
        from stubpy import generate_stub

        demo = Path(__file__).parent.parent / "demo" / "graphics.py"
        with tempfile.NamedTemporaryFile(suffix=".pyi", delete=False) as f:
            out = f.name
        c = generate_stub(str(demo), out)
        assert_valid_syntax(c)
        for cls_name in ("Shape", "Path", "Arc", "Rectangle", "Square", "Circle"):
            assert f"class {cls_name}" in c
        arc_section = c.split("class Arc")[1].split("\nclass ")[0]
        assert "angle: float" in arc_section
        assert "**kwargs" not in arc_section
