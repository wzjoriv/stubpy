"""Several callers forwarding different ``*args`` / ``**kwargs`` to one shared callee each get their own parameters."""
import ast
import textwrap

import pytest

from tests.conftest import make_stub_ctx

CALLEES = """
    def shared(x: int = 0, *, mode: str = "b", flag: bool = False, scale: float = 1.0) -> None: ...
    def middle(y: str = "m", **kw):
        return shared(**kw)
    def left(a: int = 1) -> None: ...
    def right(b: int = 2) -> None: ...
    def fan(*args, **kw):
        left(*args, **kw)
        right(**kw)
    def rec(n: int = 0, **kw):
        if n:
            return rec(n - 1, **kw)
        return shared(**kw)
    class Base:
        def _helper(self, x: int, mode: str = "b", *, deep: bool = False) -> None: ...
"""

CALLERS = {
    "f1": ("def f1(**kw):\n    return shared(**kw)\n",
           "(*, x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)"),
    "f2": ("def f2(x, **kw):\n    return shared(x, mode='a', **kw)\n",
           "(x, *, flag: bool = False, scale: float = 1.0)"),
    "f3": ("def f3(*args, **kw):\n    return shared(*args, flag=True, **kw)\n",
           "(x: int = 0, *, mode: str = 'b', scale: float = 1.0)"),
    "g1": ("def g1(**kw):\n    return middle(**kw)\n",
           "(*, y: str = 'm', x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)"),
    "g2": ("def g2(**kw):\n    return middle(y='z', **kw)\n",
           "(*, x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)"),
    "h": ("def h(**kw):\n    return fan(**kw)\n", "(*, a: int = 1, b: int = 2)"),
    "r": ("def r(**kw):\n    return rec(**kw)\n",
          "(*, n: int = 0, x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)"),
}

METHODS = """
    class A(Base):
        def run(self, **kw):
            return self._helper(1, **kw)
    class B(Base):
        def run(self, *args, **kw):
            return self._helper(*args, mode="z", **kw)
    class C(Base):
        def run(self, **kw):
            return self._helper(2, "q", **kw)
"""
METHOD_SIGNATURES = {
    "A": "(self, *, mode: str = 'b', deep: bool = False)",
    "B": "(self, x: int, *, deep: bool = False)",
    "C": "(self, *, deep: bool = False)",
}


def _signatures(stub: str) -> dict[str, str]:
    """Map each top-level function, and each class's ``run``, to its parameter list as ``ast.unparse`` writes it."""
    found: dict[str, str] = {}
    for node in ast.parse(stub).body:
        if isinstance(node, ast.FunctionDef):
            found[node.name] = f"({ast.unparse(node.args)})"
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "run":
                    found[node.name] = f"({ast.unparse(item.args)})"
    return found


def _norm(signature: str) -> str:
    """Write *signature* the way :func:`_signatures` does."""
    return f"({ast.unparse(ast.parse(f'def _{signature}: ...').body[0].args)})"


def test_each_caller_gets_its_own_parameters():
    source = textwrap.dedent(CALLEES) + "".join(code for code, _ in CALLERS.values()) + textwrap.dedent(METHODS)
    found = _signatures(make_stub_ctx(source)[0])
    for name, (_, expected) in CALLERS.items():
        assert found[name] == _norm(expected), name
    for name, expected in METHOD_SIGNATURES.items():
        assert found[name] == _norm(expected), name


@pytest.mark.parametrize("order", [list(CALLERS), list(reversed(CALLERS))])
def test_order_and_isolation_do_not_change_a_callers_stub(order):
    together = _signatures(make_stub_ctx(
        textwrap.dedent(CALLEES) + "".join(CALLERS[n][0] for n in order))[0])
    for name in order:
        alone = _signatures(make_stub_ctx(textwrap.dedent(CALLEES) + CALLERS[name][0])[0])
        assert alone[name] == together[name] == _norm(CALLERS[name][1]), name


def test_shared_callees_keep_their_own_signatures():
    found = _signatures(make_stub_ctx(textwrap.dedent(CALLEES) + "".join(c for c, _ in CALLERS.values()))[0])
    assert found["shared"] == _norm("(x: int = 0, *, mode: str = 'b', flag: bool = False, scale: float = 1.0)")
    assert found["middle"] == _norm("(y: str = 'm', *, x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)")
    assert found["fan"] == _norm("(a: int = 1, *, b: int = 2)")
    assert found["rec"] == _norm("(n: int = 0, *, x: int = 0, mode: str = 'b', flag: bool = False, scale: float = 1.0)")


def test_sibling_constructors_bind_different_arguments():
    stub, _ = make_stub_ctx("""
        class Base:
            def __init__(self, width: int, height: int = 1, *, color: str = "k") -> None: ...
        class Wide(Base):
            def __init__(self, **kw):
                super().__init__(100, **kw)
        class Square(Base):
            def __init__(self, side: int, **kw):
                super().__init__(side, side, **kw)
        class Plain(Base):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
    """)
    inits = {
        node.name: f"({ast.unparse(item.args)})"
        for node in ast.parse(stub).body if isinstance(node, ast.ClassDef)
        for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"
    }
    assert inits["Wide"] == _norm("(self, *, height: int = 1, color: str = 'k')")
    assert inits["Square"] == _norm("(self, side: int, *, color: str = 'k')")
    assert inits["Plain"] == _norm("(self, width: int, height: int = 1, *, color: str = 'k')")
    assert inits["Base"] == _norm("(self, width: int, height: int = 1, *, color: str = 'k')")
