"""Branch dispatch inside nested blocks, on attributes and through class registries; typed ``**kwargs`` reads."""
from __future__ import annotations

import textwrap

import pytest

from stubpy import Config, render
from tests.conftest import assert_valid_syntax

SHAPES = """\
    from typing import Literal


    class Alpha:
        def __init__(self, size: float) -> None: ...


    class Beta:
        def __init__(self, width: float) -> None: ...


    TABLE = {"alpha": Alpha, "beta": Beta}
"""


@pytest.fixture(params=["all", "none"])
def stub(request, tmp_path):
    """Render source text with and without importing it."""
    def _render(body: str) -> str:
        path = tmp_path / "mod.py"
        path.write_text(textwrap.dedent(SHAPES) + textwrap.dedent(body), encoding="utf-8")
        text = render(path, config=Config(imports=request.param)).text
        assert_valid_syntax(text)
        return text
    return _render


def _defs(text: str, name: str) -> list[str]:
    """The stub blocks of every ``def name`` in *text*."""
    return [part.split("\n\n")[0].split("@overload")[0].rstrip() for part in text.split(f"def {name}(")[1:]]


@pytest.mark.parametrize("opener", ["try:", "with open('x') as fh:", "for _ in range(3):", "while True:"])
def test_dispatch_inside_nested_block(stub, opener):
    text = stub(f"""
        def make(kind: Literal["alpha", "beta"], **kwargs):
            {opener}
                if kind == "alpha":
                    return Alpha(**kwargs)
                elif kind == "beta":
                    return Beta(**kwargs)
                raise ValueError(kind)
            {"except OSError:" if opener == "try:" else "if kind:"}
                raise
    """)
    alpha, beta, general = _defs(text, "make")
    assert "kind: Literal['alpha']" in alpha and alpha.endswith("-> Alpha: ...")
    assert "kind: Literal['beta']" in beta and "width: float" in beta and "size" not in beta
    assert "size: float" in general and "width: float" in general


def test_nested_dispatch_with_forwarding_outside_is_ignored(stub):
    text = stub("""
        def make(kind: Literal["alpha", "beta"], **kwargs):
            try:
                if kind == "alpha":
                    return Alpha(**kwargs)
                return Beta(**kwargs)
            except TypeError:
                return Beta(**kwargs)
    """)
    assert "@overload" not in text


def test_attribute_selector_keeps_union(stub):
    text = stub("""
        class Holder:
            kind: Literal["alpha", "beta"]

            def __init__(self, kind: Literal["alpha", "beta"]) -> None:
                self.kind = kind

            def build(self, **kwargs):
                if self.kind == "alpha":
                    return Alpha(**kwargs)
                return Beta(**kwargs)
    """)
    assert "@overload" not in text
    (only,) = _defs(text, "build")
    assert "size: float" in only and "width: float" in only and "Literal['alpha']" not in only


@pytest.mark.parametrize("call", ["cls.registry[kind]", "cls.table[kind]"])
def test_class_registry_dispatch(stub, call):
    text = stub(f"""
        class Factory:
            registry = {{"alpha": Alpha, "beta": Beta}}
            table = TABLE

            @classmethod
            def build(cls, kind: Literal["alpha", "beta"], **kwargs):
                return {call}(**kwargs)
    """)
    alpha, beta, general = _defs(text, "build")
    assert text.count("    @overload\n    @classmethod\n    def build(") == 3
    assert "kind: Literal['alpha']" in alpha and alpha.endswith("-> Alpha: ...")
    assert "kind: Literal['beta']" in beta and beta.endswith("-> Beta: ...")
    assert "**kwargs" in general


def test_self_registry_and_plain_str_selector(stub):
    text = stub("""
        class Factory:
            registry = {"alpha": Alpha, "beta": Beta}

            def make(self, kind: Literal["alpha", "beta"], **kwargs):
                return self.registry[kind](**kwargs)

            def typed(self, kind: Literal["alpha", "beta"], **kwargs):
                return type(self).registry[kind](**kwargs)

            def loose(self, kind: str, **kwargs):
                return self.registry[kind](**kwargs)

            def missing(self, kind: Literal["alpha", "beta"], **kwargs):
                return self.nowhere[kind](**kwargs)
    """)
    assert len(_defs(text, "make")) == 3 and len(_defs(text, "typed")) == 3
    assert "def loose(self, kind: str, **kwargs)" in text
    assert "def missing(self, kind: Literal['alpha', 'beta'], **kwargs)" in text


def test_typed_kwargs_reads_take_the_annotation(stub):
    text = stub("""
        def reads(**kwargs: float):
            return kwargs["a"], kwargs.get("b"), kwargs.get("c", 2.0)
    """)
    (sig,) = _defs(text, "reads")
    for part in ("a: float,", "b: float | None = None", "c: float = 2.0", "**kwargs: float"):
        assert part in sig, part
