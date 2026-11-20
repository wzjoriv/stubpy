"""Branch-aware forwarding: one ``@overload`` per literal selector, and reads of the variadics."""
from __future__ import annotations

import textwrap

import pytest

from stubpy import Config, render
from tests.conftest import assert_valid_syntax

SHAPES = """\
    from typing import Literal


    class Alpha:
        def __init__(self, size: float, fill: str = "black") -> None: ...


    class Beta:
        def __init__(self, width: float, height: float) -> None: ...


    def beta_fn(*, depth: int = 1) -> int: ...
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


def test_if_elif_gives_one_overload_per_literal(stub):
    text = stub("""
        def make(kind: Literal["alpha", "beta"], **kwargs) -> object:
            if kind == "alpha":
                return Alpha(**kwargs)
            elif kind == "beta":
                return Beta(**kwargs)
            raise ValueError(kind)
    """)
    alpha, beta, general = _defs(text, "make")
    assert text.count("@overload\ndef make(") == 3
    assert "kind: Literal['alpha']" in alpha and "size: float" in alpha and "width" not in alpha
    assert alpha.endswith("-> Alpha: ...")
    assert "kind: Literal['beta']" in beta and "height: float" in beta and "size" not in beta
    assert beta.endswith("-> Beta: ...")
    assert "kind: Literal['alpha', 'beta']" in general and "size: float" in general and "width: float" in general
    assert "from typing import" in text and "overload" in text.split("\n\n")[0]


def test_match_case_with_or_pattern_and_wildcard(stub):
    text = stub("""
        def pick(kind: str, **kwargs):
            match kind:
                case "alpha":
                    return Alpha(**kwargs)
                case "beta" | "b":
                    return Beta(**kwargs)
                case _:
                    raise ValueError(kind)
    """)
    alpha, beta, general = _defs(text, "pick")
    assert "kind: Literal['alpha']" in alpha
    assert "kind: Literal['beta', 'b']" in beta and beta.endswith("-> Beta: ...")
    assert "kind: str" in general


def test_dict_dispatch_inline_and_module_table(stub):
    text = stub("""
        TABLE = {"alpha": Alpha, "beta": Beta}

        def inline(kind: Literal["alpha", "beta"], **kwargs) -> object:
            return {"alpha": Alpha, "beta": Beta}[kind](**kwargs)

        def table(kind: Literal["alpha", "beta"], **kwargs) -> object:
            return TABLE[kind](**kwargs)
    """)
    for name in ("inline", "table"):
        alpha, beta, general = _defs(text, name)
        assert "kind: Literal['alpha']" in alpha and "size: float" in alpha
        assert "kind: Literal['beta']" in beta and beta.endswith("-> Beta: ...")
        assert "**kwargs" in general


def test_dict_dispatch_on_plain_str_keeps_open_kwargs(stub):
    text = stub("""
        def untyped(kind: str, **kwargs) -> object:
            return {"alpha": Alpha, "beta": Beta}[kind](**kwargs)
    """)
    assert "@overload" not in text
    assert "def untyped(kind: str, **kwargs) -> object: ..." in text


def test_single_case_with_fallthrough_and_default_selector(stub):
    text = stub("""
        def save(fmt: str = "alpha", **kwargs) -> object:
            if fmt == "alpha":
                return Alpha(**kwargs)
            return beta_fn(**kwargs)
    """)
    alpha, general = _defs(text, "save")
    assert "fmt: Literal['alpha'] = 'alpha'" in alpha and "depth" not in alpha
    assert "fmt: str = 'alpha'" in general and "depth: int = 1" in general and "size: float" in general


def test_non_returned_branch_keeps_own_return(stub):
    text = stub("""
        def run(mode: Literal["a", "b"], **kwargs) -> None:
            if mode == "a":
                beta_fn(**kwargs)
            else:
                Alpha(**kwargs)
            if mode == "b":
                pass
    """)
    assert "@overload" not in text or all(d.endswith("-> None: ...") for d in _defs(text, "run"))


def test_selector_not_a_parameter_keeps_union(stub):
    text = stub("""
        MODE = "alpha"

        def build(**kwargs) -> object:
            if MODE == "alpha":
                return Alpha(**kwargs)
            return Beta(**kwargs)
    """)
    assert "@overload" not in text
    (only,) = _defs(text, "build")
    assert "size: float" in only and "width: float" in only


def test_method_dispatch_gets_overloads(stub):
    text = stub("""
        class Factory:
            def build(self, kind: Literal["alpha", "beta"], **kwargs):
                if kind == "alpha":
                    return Alpha(**kwargs)
                return Beta(**kwargs)
    """)
    alpha, general = _defs(text, "build")
    assert "    @overload\n    def build(" in text
    assert "self," in alpha and "kind: Literal['alpha']" in alpha and alpha.endswith("-> Alpha: ...")
    assert "width: float" in general


def test_kwargs_reads_become_keyword_only(stub):
    text = stub("""
        def reads(**kwargs):
            size = kwargs.get("size", 3)
            ratio = kwargs.get("ratio", 0.5)
            label = kwargs.get("label")
            name = kwargs["name"]
            maybe = kwargs["maybe"] if "maybe" in kwargs else None
            return size, ratio, label, name, maybe
    """)
    (sig,) = _defs(text, "reads")
    for part in ("size: int = 3", "ratio: float = 0.5", "label: Any = None", "name: Any,", "maybe: Any = ...",
                 "**kwargs"):
        assert part in sig, part


def test_kwargs_read_also_forwarded_is_not_doubled(stub):
    text = stub("""
        def both(**kwargs):
            if kwargs.get("fill") == "red":
                pass
            extra = kwargs.get("extra", "x")
            return Alpha(**kwargs), extra
    """)
    (sig,) = _defs(text, "both")
    assert sig.count("fill") == 1 and "fill: str = 'black'" in sig
    assert "extra: str = 'x'" in sig


def test_popped_key_stays_a_consumed_parameter(stub):
    text = stub("""
        def popper(**kwargs):
            level = kwargs.pop("level", 2)
            return Alpha(**kwargs), level
    """)
    (sig,) = _defs(text, "popper")
    assert "level: int = 2" in sig and sig.count("level") == 1 and "size: float" in sig


def test_args_index_reads_become_positional_only(stub):
    text = stub("""
        def head(*args, **kwargs):
            first = args[0]
            third = args[2]
            return first, third
    """)
    (sig,) = _defs(text, "head")
    assert "args_0: Any" in sig and "args_1: Any" in sig and "args_2: Any" in sig
    assert sig.index("args_2") < sig.index("/") < sig.index("*args")


def test_args_reads_skipped_when_args_is_forwarded_or_typed(stub):
    text = stub("""
        def fwd(*args):
            first = args[0]
            return Beta(*args), first

        def typed(*items: int) -> int:
            return items[0]
    """)
    assert "args_0" not in text and "items_0" not in text
    assert "def typed(*items: int) -> int: ..." in text
