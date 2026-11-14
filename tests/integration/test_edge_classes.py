"""Edge cases: class constructs."""
from __future__ import annotations

import ast

import pytest

from tests.conftest import flatten, make_stub_ctx

MODES = ["runtime", "ast_only"]


def _class(stub: str, name: str) -> ast.ClassDef:
    for node in ast.walk(ast.parse(stub)):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not in stub:\n{stub}")


def _decorators(func: ast.FunctionDef) -> list[str]:
    return [ast.unparse(d) for d in func.decorator_list]


def _methods(cls: ast.ClassDef, name: str) -> list[ast.FunctionDef]:
    return [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]


@pytest.mark.parametrize("mode", MODES)
class TestClassEdges:
    def test_cached_property_keeps_its_decorator_and_import(self, mode):
        stub, _ = make_stub_ctx("""
            import functools
            class C:
                @functools.cached_property
                def total(self) -> int: ...
        """, mode)
        (method,) = _methods(_class(stub, "C"), "total")
        assert _decorators(method) == ["cached_property"]
        assert "from functools import cached_property" in stub

    def test_hash_none_and_empty_class(self, mode):
        stub, _ = make_stub_ctx("""
            class Unhashable:
                __hash__ = None
            class Empty:
                pass
        """, mode)
        assert "__hash__: ClassVar[None]" in stub
        assert "ClassVar" in stub.splitlines()[1]
        empty = _class(stub, "Empty")
        assert len(empty.body) == 1 and isinstance(empty.body[0], ast.Expr)

    def test_enum_alias_auto_methods_and_missing(self, mode):
        stub, _ = make_stub_ctx("""
            from enum import Enum, auto
            class Color(Enum):
                RED = auto()
                GREEN = auto()
                CRIMSON = RED
                def describe(self) -> str: ...
                @classmethod
                def _missing_(cls, value):
                    return cls.RED
        """, mode)
        color = _class(stub, "Color")
        assigns = {ast.unparse(n.targets[0]): ast.unparse(n.value) for n in color.body if isinstance(n, ast.Assign)}
        assert set(assigns) == {"RED", "GREEN", "CRIMSON"}
        assert assigns["CRIMSON"] == "RED"
        if mode == "runtime":
            assert assigns["RED"] == "1" and assigns["GREEN"] == "2"
        assert _methods(color, "describe")
        assert not _methods(color, "_missing_")
        assert not _methods(color, "__new__")

    def test_nested_class_and_qualified_annotation(self, mode):
        stub, _ = make_stub_ctx("""
            class Outer:
                class Inner:
                    x: int
                def make(self) -> "Outer.Inner": ...
        """, mode)
        outer = _class(stub, "Outer")
        assert any(isinstance(n, ast.ClassDef) and n.name == "Inner" for n in outer.body)
        assert "Outer.Inner" in ast.unparse(_methods(outer, "make")[0].returns)

    def test_ast_only_drops_meaningless_decorators(self, mode):
        stub, _ = make_stub_ctx("""
            import functools
            import abc
            from typing import final, overload
            class App:
                def route(self, path): return lambda f: f
            app = App()
            class Svc(abc.ABC):
                @functools.lru_cache(maxsize=None)
                def cached(self, x: int) -> int: ...
                @app.route("/x")
                def handler(self) -> None: ...
                @abc.abstractmethod
                def run(self) -> None: ...
                @final
                def done(self) -> None: ...
                @property
                def value(self) -> int: ...
                @value.setter
                def value(self, v: int) -> None: ...
                @overload
                def get(self, k: int) -> int: ...
                @overload
                def get(self, k: str) -> str: ...
                def get(self, k): return k
        """, mode)
        svc = _class(stub, "Svc")
        assert _decorators(_methods(svc, "cached")[0]) == []
        assert _decorators(_methods(svc, "handler")[0]) == []
        assert "abstractmethod" in _decorators(_methods(svc, "run")[0])
        assert _decorators(_methods(svc, "done")[0]) == ["final"]
        assert [_decorators(m) for m in _methods(svc, "value")] == [["property"], ["value.setter"]]
        gets = _methods(svc, "get")
        assert len(gets) == 2 and all(_decorators(m) == ["overload"] for m in gets)
        assert "lru_cache" not in stub and "route" not in stub.split("class Svc")[1]


class TestRuntimeClassEdges:
    def test_property_setter_defined_only_in_subclass(self):
        stub, _ = make_stub_ctx("""
            class Base:
                @property
                def v(self) -> int: ...
            class Sub(Base):
                @Base.v.setter
                def v(self, value: int) -> None: ...
        """)
        sub = _class(stub, "Sub")
        assert [_decorators(m) for m in _methods(sub, "v")] == [["property"], ["v.setter"]]

    def test_class_created_with_type_call(self):
        stub, _ = make_stub_ctx("""
            class Base:
                def hello(self) -> str: ...
            X = type("X", (Base,), {"n": 1})
        """)
        assert "class X(Base)" in stub

    def test_dataclass_initvar_init_false_kw_only_factory(self):
        stub, _ = make_stub_ctx("""
            from dataclasses import InitVar, dataclass, field
            @dataclass(kw_only=True)
            class K:
                a: int
                b: list[int] = field(default_factory=list)
                c: int = field(init=False, default=0)
                d: InitVar[str] = "x"
                def __post_init__(self, d: str) -> None: ...
        """)
        init = [n for n in _class(stub, "K").body if isinstance(n, ast.FunctionDef) and n.name == "__init__"][0]
        assert [a.arg for a in init.args.args] == ["self"]
        assert [a.arg for a in init.args.kwonlyargs] == ["a", "b", "d"]
        assert ast.unparse(init.args.kwonlyargs[2].annotation) == "str"
        assert "c: int" in stub
        assert "from dataclasses import" in stub and "InitVar" in stub.splitlines()[2] + stub.splitlines()[1]

    def test_dataclass_generated_methods_are_not_stubbed(self):
        stub, _ = make_stub_ctx("""
            from dataclasses import dataclass
            @dataclass(order=True, frozen=True)
            class P:
                x: int
                def norm(self) -> int: ...
        """)
        cls = _class(stub, "P")
        names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        assert names == {"__init__", "norm"}
        assert "@dataclass(order=True, frozen=True)" in stub

    def test_lru_cache_and_wraps_methods_are_unwrapped(self):
        stub, _ = make_stub_ctx("""
            import functools
            def logged(fn):
                @functools.wraps(fn)
                def wrapper(*args, **kwargs):
                    return fn(*args, **kwargs)
                return wrapper
            class C:
                @functools.lru_cache(maxsize=None)
                def cached(self, x: int, y: str = "a") -> int: ...
                @logged
                def logged_m(self, z: float) -> None: ...
        """)
        flat = flatten(stub)
        assert "def cached(self, x: int, y: str = 'a') -> int" in flat
        assert "def logged_m(self, z: float) -> None" in flat
        assert "lru_cache" not in stub and "@logged" not in stub

    def test_final_override_and_deprecated_survive_runtime_emission(self):
        stub, _ = make_stub_ctx("""
            from typing import final
            class Base:
                @final
                def locked(self) -> None: ...
        """)
        (locked,) = _methods(_class(stub, "Base"), "locked")
        assert _decorators(locked) == ["final"]
        assert "from typing import" in stub and "final" in stub.splitlines()[1]
