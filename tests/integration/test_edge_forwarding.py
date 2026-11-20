"""Edge cases: ``**kwargs`` / ``*args`` forwarding."""
from __future__ import annotations

import ast

from stubpy.state.diagnostics import Level
from tests.conftest import make_stub_ctx


def _signature(stub: str, qualname: str) -> ast.arguments:
    """Return the arguments of ``func`` or ``Class.method`` in *stub*."""
    tree = ast.parse(stub)
    scope: list[ast.stmt] = tree.body
    *owners, name = qualname.split(".")
    for owner in owners:
        scope = next(n for n in scope if isinstance(n, ast.ClassDef) and n.name == owner).body
    funcs = [n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert funcs, f"{qualname} not in stub:\n{stub}"
    return funcs[-1].args


def _names(args: ast.arguments) -> list[str]:
    names = [a.arg for a in args.posonlyargs + args.args if a.arg not in ("self", "cls")]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return names


def _kwonly(args: ast.arguments) -> list[str]:
    return [a.arg for a in args.kwonlyargs]


class TestForwardingEdges:
    def test_diamond_mro_union_first_in_mro_wins(self):
        stub, _ = make_stub_ctx("""
            class Base:
                def __init__(self, base: int = 0) -> None: ...
            class B(Base):
                def __init__(self, b: int = 1, shared: str = "b", **kw) -> None:
                    super().__init__(**kw)
            class C(Base):
                def __init__(self, c: int = 2, shared: int = 3, **kw) -> None:
                    super().__init__(**kw)
            class D(B, C):
                def __init__(self, d: int = 4, **kw) -> None:
                    super().__init__(**kw)
        """)
        args = _signature(stub, "D.__init__")
        names = _names(args)
        assert names == ["d", "b", "shared", "c", "base"]
        shared = next(a for a in args.kwonlyargs if a.arg == "shared")
        assert ast.unparse(shared.annotation) == "str"

    def test_popped_and_deleted_keys_are_own_params_once(self):
        stub, _ = make_stub_ctx("""
            def target(x: int = 0, y: int = 0, z: int = 0) -> None: ...
            def f(**kw):
                x = kw.pop("x")
                del kw["y"]
                return target(**kw)
        """)
        names = _names(_signature(stub, "f"))
        assert names.count("x") == 1 and names.count("y") == 1
        assert "z" in names and "**kw" not in names

    def test_pop_with_default_keeps_default(self):
        stub, _ = make_stub_ctx("""
            def target(z: int = 0) -> None: ...
            def f(**kw):
                level = kw.pop("level", 3)
                return target(**kw)
        """)
        assert "level: int = 3" in stub

    def test_injected_key_is_not_in_signature(self):
        stub, _ = make_stub_ctx("""
            def target(timeout: float = 1.0, retries: int = 2) -> None: ...
            def f(**kw):
                kw["timeout"] = 5
                return target(**kw)
        """)
        names = _names(_signature(stub, "f"))
        assert "timeout" not in names
        assert "retries" in names

    def test_direct_recursion_terminates(self):
        stub, _ = make_stub_ctx("""
            def f(a: int = 1, **kw):
                return f(**kw)
        """)
        assert _names(_signature(stub, "f"))[0] == "a"

    def test_mutual_recursion_terminates(self):
        stub, _ = make_stub_ctx("""
            def g(x: int = 0, **kw):
                return h(**kw)
            def h(y: int = 0, **kw):
                return g(**kw)
        """)
        assert "x" in _names(_signature(stub, "g"))
        assert "y" in _names(_signature(stub, "h"))

    def test_forwarding_to_partial_drops_or_defaults_bound_args(self):
        stub, _ = make_stub_ctx("""
            import functools
            def g(a: int, b: str) -> None: ...
            g2 = functools.partial(g, a=1)
            def f(**kw):
                return g2(**kw)
        """)
        args = _signature(stub, "f")
        names = _names(args)
        assert "b" in names
        if "a" in names:
            a_index = [x.arg for x in args.kwonlyargs].index("a")
            assert args.kw_defaults[a_index] is not None

    def test_type_self_call_is_a_cls_call(self):
        stub, _ = make_stub_ctx("""
            class P:
                def __init__(self, x: int, y: int = 0) -> None: ...
                def clone(self, **kw) -> "P":
                    return type(self)(**kw)
                @classmethod
                def make(cls, **kw) -> "P":
                    return cls(**kw)
        """)
        assert _names(_signature(stub, "P.clone")) == ["x", "y"]
        assert _names(_signature(stub, "P.make")) == ["x", "y"]

    def test_explicit_base_init_resolves_to_that_base(self):
        stub, _ = make_stub_ctx("""
            class Base:
                def __init__(self, a: int = 1) -> None: ...
            class Mixin:
                def __init__(self, m: int = 2) -> None: ...
            class Child(Mixin, Base):
                def __init__(self, **kw) -> None:
                    Base.__init__(self, **kw)
        """)
        names = _names(_signature(stub, "Child.__init__"))
        assert "a" in names and "m" not in names

    def test_dynamic_callee_keeps_kwargs_with_warning(self):
        stub, ctx = make_stub_ctx("""
            class Svc:
                def call(self, name: str, **kw):
                    return getattr(self, name)(**kw)
            def g(**kw):
                return dict(**{k: v for k, v in kw.items()})
        """)
        assert "**kw" in _names(_signature(stub, "Svc.call"))
        assert "**kw" in _names(_signature(stub, "g"))
        warned = {d.symbol for d in ctx.diagnostics if d.level == Level.WARNING}
        assert {"Svc.call", "g"} <= warned

    def test_callee_with_its_own_kwargs_keeps_kwargs(self):
        stub, _ = make_stub_ctx("""
            def target(a: int = 1, **extra) -> None: ...
            def f(**kw):
                return target(**kw)
        """)
        assert _names(_signature(stub, "f")) == ["a", "**kw"]

    def test_own_and_forwarded_param_are_not_duplicated(self):
        stub, _ = make_stub_ctx("""
            def target(x: int = 0, y: int = 0) -> None: ...
            def f(x: str = "own", **kw):
                return target(x=1, **kw)
        """)
        names = _names(_signature(stub, "f"))
        assert names.count("x") == 1 and "y" in names

    def test_metaclass_call_does_not_replace_init(self):
        stub, _ = make_stub_ctx("""
            class Meta(type):
                def __call__(cls, *args, **kwargs):
                    return super().__call__(*args, **kwargs)
            class W(metaclass=Meta):
                def __init__(self, size: int = 1) -> None: ...
        """)
        assert _names(_signature(stub, "W.__init__")) == ["size"]
        assert "class W(metaclass=Meta)" in stub

    def test_params_reached_only_through_kwargs_are_keyword_only(self):
        stub, _ = make_stub_ctx("""
            class Base:
                def __init__(self, x: int = 0, y: int = 0) -> None: ...
            class Child(Base):
                def __init__(self, label: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        args = _signature(stub, "Child.__init__")
        assert [a.arg for a in args.args] == ["self", "label"]
        assert _kwonly(args) == ["x", "y"]

    def test_positional_arguments_at_super_call_bind_parent_params(self):
        stub, _ = make_stub_ctx("""
            class Ellipse:
                def __init__(self, cx: float, cy: float, rx: float, ry: float, *, name: str = "") -> None: ...
            class Circle(Ellipse):
                def __init__(self, cx: float, cy: float, r: float, **kwargs) -> None:
                    super().__init__(cx, cy, r, r, **kwargs)
        """)
        assert _names(_signature(stub, "Circle.__init__")) == ["cx", "cy", "r", "name"]

    def test_args_and_kwargs_forwarded_keep_positional_params(self):
        stub, _ = make_stub_ctx("""
            class Rect:
                def __init__(self, x: float = 0.0, y: float = 0.0, *, name: str = "") -> None: ...
            class Rounded(Rect):
                def __init__(self, *args, radius: float = 4.0, **kwargs) -> None:
                    super().__init__(*args, **kwargs)
            class Badge(Rounded):
                def __init__(self, label: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """)
        rounded = _signature(stub, "Rounded.__init__")
        assert [a.arg for a in rounded.args] == ["self", "x", "y"]
        badge = _signature(stub, "Badge.__init__")
        assert [a.arg for a in badge.args] == ["self", "label"]
        assert set(_kwonly(badge)) == {"radius", "x", "y", "name"}

    def test_instance_method_of_constructed_class(self):
        stub, _ = make_stub_ctx("""
            class Writer:
                def write(self, data: bytes, *, level: int = 6) -> None: ...
            def save(data: bytes, **kwargs) -> None:
                Writer().write(data, **kwargs)
        """)
        assert _names(_signature(stub, "save")) == ["data", "level"]

    def test_unknown_starred_positional_keeps_kwargs(self):
        stub, _ = make_stub_ctx("""
            class Color:
                def __init__(self, r: int, g: int, b: int, *, alpha: int = 255) -> None: ...
                @classmethod
                def parse(cls, text: str, **kwargs) -> "Color":
                    parts = [int(p) for p in text.split(",")]
                    return cls(*parts, **kwargs)
        """)
        names = _names(_signature(stub, "Color.parse"))
        assert "r" not in names
        assert "alpha" in names and "**kwargs" in names
