"""``--mode ast`` back-traces ``*args`` / ``**kwargs`` from source alone and matches ``runtime`` where the source suffices."""
from __future__ import annotations

import ast
import sys
import textwrap
from pathlib import Path

import pytest

import stubpy
from stubpy import Config

MODULES = {
    "__init__.py": "",
    "base.py": '''
        from enum import Enum
        from typing import Optional

        class Color(Enum):
            RED = 1

        class Element:
            def __init__(self, id: str = "", color: Color = Color.RED, tag: Optional[str] = None): ...

        class Styled(Element):
            def __init__(self, fill: str = "none", *, stroke: str = "black", **kwargs):
                super().__init__(**kwargs)

        def connect(host: str, port: int = 80, *, timeout: float = 5.0) -> None: ...

        def positional(a: int, b: int, /, c: int = 0, *, d: int = 1) -> None: ...
    ''',
    "sub/__init__.py": "",
    "sub/net.py": '''
        from dataclasses import dataclass, field
        from typing import NamedTuple, TypedDict

        class Client:
            def __init__(self, url: str, retries: int = 3): ...

        @dataclass
        class Point:
            x: int
            y: int = 0
            tags: list = field(default_factory=list)

        class Pair(NamedTuple):
            a: int
            b: str = "x"

        class Options(TypedDict, total=False):
            color: str
            width: int
    ''',
    "shapes.py": '''
        import functools
        from collections import OrderedDict
        from typing import Any

        try:
            from typing import Unpack
        except ImportError:
            from typing_extensions import Unpack

        import pk.sub.net
        from . import base, sub
        from .base import Element, Styled, connect
        from .sub import net
        from .sub.net import Options

        class Circle(Styled):
            def __init__(self, r: float, **kwargs):
                super().__init__(**kwargs)

            @classmethod
            def unit(cls, **kwargs) -> "Circle":
                return cls(1.0, **kwargs)

            def copy(self, **kwargs) -> "Circle":
                return type(self)(2.0, **kwargs)

            def restyle(self, **kwargs) -> None:
                self.configure(**kwargs)

            def configure(self, *, wrap: bool = False, indent: int = 0) -> None: ...

        class Explicit(Element):
            def __init__(self, label: str, **kw):
                kw.pop("tag", None)
                Element.__init__(self, **kw)

        class Diamond(Styled, OrderedDict):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

        def fetch(url: str, **kw) -> bytes:
            connect("h", **kw)
            return b""

        def fetch_mod(**kw):
            base.connect("h", **kw)

        def fetch_pkg(**kw):
            pk.sub.net.Client("u", **kw)

        def fetch_sub(**kw):
            sub.net.Client(**kw)

        def fetch_local(**kw):
            from .sub import net as n
            return n.Client(**kw)

        def fetch_local_import(**kw):
            import pk.base
            pk.base.connect("x", **kw)

        def popped(**kw):
            kw.pop("port", None)
            del kw["timeout"]
            connect("h", **kw)

        def merged(**kw):
            connect(**{**kw, "port": 1})

        quick = functools.partial(connect, port=8080)

        def via_partial(**kw):
            quick("h", **kw)

        def pos_args(*args, **kw):
            base.positional(*args, **kw)

        def point(**kw):
            return net.Point(**kw)

        def pair(**kw):
            return net.Pair(**kw)

        def options(**kw):
            return net.Options(**kw)

        def styled(**kwargs: Unpack[Options]) -> None: ...

        def into_unpack(name: str, **kwargs):
            styled(**kwargs)

        def recursive(**kw):
            recursive(**kw)

        def chained(**kw):
            fetch("x", **kw)
    ''',
}

COMPARED = [
    "Circle.__init__", "Circle.unit", "Circle.copy", "Circle.restyle", "Explicit.__init__", "Diamond.__init__",
    "fetch", "fetch_mod", "fetch_pkg", "fetch_sub", "fetch_local", "fetch_local_import", "popped", "merged",
    "quick", "via_partial", "pos_args", "point", "pair", "options", "styled", "into_unpack", "recursive", "chained",
]


def _signatures(stub: str) -> dict[str, list[tuple]]:
    """Map ``Class.method`` / ``function`` to its parameters: ``(kind, name, annotation, default)``."""
    out: dict[str, list[tuple]] = {}

    def params(fn: ast.FunctionDef) -> list[tuple]:
        a = fn.args
        defaults = [None] * (len(a.posonlyargs) + len(a.args) - len(a.defaults)) + list(a.defaults)
        rows = []
        for kind, group in (("pos_only", a.posonlyargs), ("pos", a.args)):
            for arg in group:
                rows.append((kind, arg.arg, arg.annotation, defaults.pop(0)))
        if a.vararg:
            rows.append(("*", a.vararg.arg, a.vararg.annotation, None))
        rows += [("kw", k.arg, k.annotation, d) for k, d in zip(a.kwonlyargs, a.kw_defaults, strict=True)]
        if a.kwarg:
            rows.append(("**", a.kwarg.arg, a.kwarg.annotation, None))
        return [(k, n, ast.unparse(t) if t else None, ast.unparse(d) if d else None) for k, n, t, d in rows]

    for node in ast.parse(stub).body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = params(node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    out[f"{node.name}.{item.name}"] = params(item)
    return out


@pytest.fixture(scope="module")
def stubs(tmp_path_factory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("astbt") / "src"
    pkg = root / "pk"
    for rel, text in MODULES.items():
        path = pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    out = {}
    for mode in ("runtime", "ast"):
        target = root.parent / f"out_{mode}"
        report = stubpy.generate(str(pkg), str(target), config=Config(mode=mode))
        assert report.ok, report.summary()
        out[mode] = (target / "pk" / "shapes.pyi").read_text(encoding="utf-8")
    for name in [m for m in sys.modules if m == "pk" or m.startswith("pk.")]:
        del sys.modules[name]
    return out


@pytest.mark.parametrize("name", COMPARED)
def test_ast_matches_runtime(stubs, name):
    runtime, static = _signatures(stubs["runtime"]), _signatures(stubs["ast"])
    assert static[name] == runtime[name]


def test_ast_expands_through_the_mro_across_modules(stubs):
    sig = _signatures(stubs["ast"])["Circle.__init__"]
    assert [row[1] for row in sig] == ["self", "r", "fill", "stroke", "id", "color", "tag"]
    assert ("kw", "color", "Color", "Color.RED") in sig
    assert "from .base import Color, Element, Styled" in stubs["ast"]


def test_ast_stdlib_base_without_the_method_is_skipped(stubs):
    assert "stroke" in [row[1] for row in _signatures(stubs["ast"])["Diamond.__init__"]]


@pytest.mark.parametrize("name", ["fetch_mod", "fetch_pkg", "fetch_sub", "fetch_local", "fetch_local_import"])
def test_attribute_callees_resolve(stubs, name):
    for mode in ("runtime", "ast"):
        assert all(row[0] != "**" for row in _signatures(stubs[mode])[name]), mode


def test_pop_del_and_merge(stubs):
    sig = _signatures(stubs["ast"])
    assert sorted(row[1] for row in sig["popped"]) == ["port", "timeout"]
    assert [row[1] for row in sig["merged"]] == ["host", "timeout"]


def test_partial_variable_and_positional_only(stubs):
    sig = _signatures(stubs["ast"])
    assert ("kw", "port", "int", "8080") in sig["quick"]
    assert ("kw", "port", "int", "8080") in sig["via_partial"]
    assert [row[:2] for row in sig["pos_args"]] == [("pos_only", "a"), ("pos_only", "b"), ("pos", "c"), ("kw", "d")]


def test_typed_constructors_and_unpack(stubs):
    sig = _signatures(stubs["ast"])
    assert [row[1] for row in sig["point"]] == ["x", "y", "tags"]
    assert [row[1] for row in sig["pair"]] == ["a", "b"]
    assert [row[1:] for row in sig["options"]] == [("color", "str", "..."), ("width", "int", "...")]
    assert sig["styled"] == [("**", "kwargs", "Unpack[Options]", None)]
    assert [row[1] for row in sig["into_unpack"]] == ["name", "color", "width"]


def test_recursion_keeps_kwargs(stubs):
    assert _signatures(stubs["ast"])["recursive"] == [("**", "kw", None, None)]


def test_resolve_kwargs_off_keeps_ast_variadics(tmp_path):
    (tmp_path / "m.py").write_text("def f(a: int = 0): ...\ndef g(**kw):\n    f(**kw)\n", encoding="utf-8")
    text = stubpy.render(str(tmp_path / "m.py"), config=Config(mode="ast", resolve_kwargs=False)).text
    assert "def g(**kw): ..." in text


def test_overloaded_callee_variants_copied(tmp_path):
    src = '''
        from typing import overload

        @overload
        def g(x: int) -> int: ...
        @overload
        def g(x: str) -> str: ...
        def g(x): return x

        def f(*args, **kwargs):
            return g(*args, **kwargs)

        class B:
            @overload
            def m(self, a: int) -> int: ...
            @overload
            def m(self, a: str) -> str: ...
            def m(self, a): return a

        class C(B):
            def m(self, *args, **kwargs):
                return super().m(*args, **kwargs)
    '''
    path = tmp_path / "ov.py"
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    for mode in ("runtime", "ast"):
        text = stubpy.render(str(path), config=Config(mode=mode)).text
        assert "@overload\ndef f(x: int) -> int: ...\n@overload\ndef f(x: str) -> str: ..." in text, mode
        assert "class C(B):\n    @overload\n    def m(self, a: int) -> int: ..." in text, mode


def test_index_is_shared_by_a_run(tmp_path):
    from stubpy.resolve.static import SourceIndex

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    index = SourceIndex()
    first = index.module_at(Path(tmp_path / "a.py"))
    assert index.module_at(tmp_path / "a.py") is first and first.name == "a"


def test_paramspec_decorator_keeps_the_wrapped_signature(tmp_path):
    src = '''
        from typing import Callable, ParamSpec, TypeVar
        P = ParamSpec("P")
        R = TypeVar("R")

        def logged(fn: Callable[P, R]) -> Callable[P, R]:
            def inner(*args: P.args, **kwargs: P.kwargs) -> R:
                return fn(*args, **kwargs)
            return inner

        @logged
        def area(w: float, h: float = 1.0) -> float: ...

        class K:
            @logged
            def m(self, x: int) -> str: ...
    '''
    path = tmp_path / "ps.py"
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    for mode in ("runtime", "ast"):
        text = stubpy.render(str(path), config=Config(mode=mode)).text
        assert "def area(w: float, h: float = 1.0) -> float: ..." in text, mode
        assert "def m(self, x: int) -> str: ..." in text, mode


def test_dynamic_forwarding_warns_in_both_modes(tmp_path):
    src = '''
        def inner(a: int = 0): ...

        def f(**kw):
            inner(**{k: v for k, v in kw.items()})

        class C:
            def m(self, name, **kw):
                getattr(self, name)(**kw)
    '''
    path = tmp_path / "dyn.py"
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    for mode in ("runtime", "ast"):
        result = stubpy.render(str(path), config=Config(mode=mode))
        assert "def f(**kw): ..." in result.text and "def m(self, name, **kw): ..." in result.text
        assert {w.symbol for w in result.warnings} >= {"f", "C.m"}, mode
