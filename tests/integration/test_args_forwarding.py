"""``*args`` forwarding, with and without importing: every call shape gets a correct, positional-only expansion."""
from __future__ import annotations

import ast

import pytest

from tests.conftest import make_stub_ctx


def _has_signature(obj) -> bool:
    import inspect
    try:
        inspect.signature(obj)
    except (TypeError, ValueError):
        return False
    return True


BOTH = pytest.mark.parametrize("imports", ["all", "none"])

SOURCE = '''
import functools
from typing import Callable, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")


def target(a: int, b: str = "x", /, c: float = 1.0, *rest: bytes, k: bool = False) -> None: ...
def pos_only(a: int, b: int, /) -> None: ...
def kw_only(*, k: int) -> None: ...
def typed_items(*items: int) -> None: ...


def f_args(*args):
    return target(*args)


def f_prebound(x, *args):
    return target(x, *args)


def f_rest(*args):
    first, *rest = args
    return pos_only(first, *rest)


def f_slice(*args):
    return target(*args[1:])


def f_kwonly(*args):
    return kw_only(*args)


def f_typed(*items: int):
    return typed_items(*items)


def f_split(*args, **kwargs):
    pos_only(*args)
    kw_only(**kwargs)


class Base:
    def __init__(self, width: int, height: int = 2, /, depth: float = 0.0) -> None: ...

    def m(self, a: int, b: str = "y") -> None: ...


class Child(Base):
    def __init__(self, *args):
        super().__init__(*args)

    def call(self, *args):
        return self.m(*args)

    @classmethod
    def make(cls, *args):
        return cls(*args)


@overload
def ov(x: int) -> int: ...
@overload
def ov(x: str) -> str: ...
def ov(x): return x


def f_ov(*args):
    return ov(*args)


part = functools.partial(target, 1)


def f_part(*args):
    return part(*args)


def deco(fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)
    return inner


@deco
def decorated(a: int, b: int = 0) -> int: ...


def f_deco(*args):
    return decorated(*args)
'''


def _sig(stub: str, name: str, cls: str | None = None) -> str:
    tree = ast.parse(stub)
    body = tree.body if cls is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls).body
    fns = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == name]
    return " | ".join(ast.unparse(f.args) for f in fns)


@pytest.fixture(params=["all", "none"])
def stub(request):
    return make_stub_ctx(SOURCE, imports=request.param)[0]


@pytest.mark.parametrize("name, expected", [
    ("f_args", "a: int, b: str='x', c: float=1.0, /, *args: bytes"),
    ("f_prebound", "x, b: str='x', c: float=1.0, /, *args: bytes"),
    ("f_rest", "a: int, b: int, /"),
    ("f_slice", "*args"),
    ("f_kwonly", ""),
    ("f_typed", "*items: int"),
    ("f_split", "a: int, b: int, /, *, k: int"),
    ("f_ov", "x: int, / | x: str, /"),
    ("f_part", "b: str='x', c: float=1.0, /, *args: bytes"),
    ("f_deco", "a: int, b: int=0, /"),
])
def test_functions(stub, name, expected):
    assert _sig(stub, name) == expected


@pytest.mark.parametrize("name, expected", [
    ("__init__", "self, width: int, height: int=2, depth: float=0.0, /"),
    ("call", "self, a: int, b: str='y', /"),
    ("make", "cls, width: int, height: int=2, depth: float=0.0, /"),
])
def test_methods(stub, name, expected):
    assert _sig(stub, name, "Child") == expected


@BOTH
def test_resolve_args_off_keeps_args(imports):
    stub, _ = make_stub_ctx(SOURCE, imports=imports, resolve_args=False)
    assert _sig(stub, "f_args") == "*args"
    assert _sig(stub, "__init__", "Child") == "self, *args"


@BOTH
def test_resolve_kwargs_off_keeps_kwargs_but_args_still_resolve(imports):
    stub, _ = make_stub_ctx(SOURCE, imports=imports, resolve_kwargs=False)
    assert _sig(stub, "f_split") == "*args, **kwargs"


@BOTH
@pytest.mark.skipif(not _has_signature(__import__('math').atan2), reason="this interpreter's math.atan2 has no text signature")
def test_compiled_style_callee_through_args(imports):
    stub, _ = make_stub_ctx('''
        import math
        def hyp(*args):
            return math.hypot(*args)
        def angle(*args):
            return math.atan2(*args)
    ''', imports=imports)
    assert _sig(stub, "hyp") == "*args"
    import inspect
    import math
    names = ", ".join(inspect.signature(math.atan2).parameters)
    assert _sig(stub, "angle") == f"{names}, /"
