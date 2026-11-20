"""
Inferred types in stubs: safe returns and docstring types of forwarded keywords.
"""
from __future__ import annotations

import pytest

from tests.conftest import flatten, make_stub_ctx

RETURNS = '''
class Builder:
    def chain(self):
        self.n = 1
        return self

    def copy(self):
        return Builder()

    def label(self):
        return f"b{self.n}"

    def reset(self):
        self.n = 0

    def unknown(self, other):
        return other


def count(items):
    return len(items)


def make():
    return Builder()
'''

FORWARDED = '''
def target(a, b=1, c=None, d=None, e=None):
    """Do something.

    Parameters
    ----------
    a : int
        First.
    c : str, optional
        Third.
    d : array-like
        Fourth.
    """


class Widget:
    """A widget.

    Parameters
    ----------
    size : float
        The size.
    """

    def __init__(self, size=None):
        self.size = size


def outer(a, **kwargs):
    """Outer.

    Parameters
    ----------
    a : bytes
        Own parameter.
    """
    return target(a, **kwargs)


def build(**kwargs):
    return Widget(**kwargs)
'''


@pytest.mark.parametrize("imports", ["all", "none"])
def test_safe_returns(imports):
    stub, _ = make_stub_ctx(RETURNS, imports=imports)
    flat = flatten(stub)
    assert "def chain(self) -> Builder: ..." in flat
    assert "def copy(self) -> Builder: ..." in flat
    assert "def label(self) -> str: ..." in flat
    assert "def reset(self) -> None: ..." in flat
    assert "def unknown(self, other): ..." in flat
    assert "def count(items) -> int: ..." in flat
    assert "def make() -> Builder: ..." in flat


@pytest.mark.parametrize("imports", ["all", "none"])
def test_return_self_is_self_from_311(imports):
    stub, _ = make_stub_ctx(RETURNS, imports=imports, target_python="3.11")
    assert "def chain(self) -> Self: ..." in stub
    assert "from typing import Self" in stub


def test_unknown_class_call_is_not_inferred():
    stub, _ = make_stub_ctx("from pathlib import Path\n\ndef f(x):\n    return Path(x)\n")
    assert "def f(x): ..." in stub


def test_written_annotation_wins():
    stub, _ = make_stub_ctx("def f(x) -> object:\n    return 1\n")
    assert "def f(x) -> object: ..." in stub


def test_forwarded_keywords_take_callee_docstring_types():
    stub, _ = make_stub_ctx(FORWARDED)
    flat = flatten(stub)
    outer = next(line for line in flat.splitlines() if line.startswith("def outer("))
    assert "b: int = 1" in outer
    assert "c: str | None = None" in outer
    assert "d=None" in outer and "e=None" in outer
    assert "a," in outer and "a: bytes" not in outer
    build = next(line for line in flat.splitlines() if line.startswith("def build("))
    assert "size: float | None = None" in build


def test_own_docstring_types_still_need_infer_types():
    stub, _ = make_stub_ctx(FORWARDED, infer_types=True)
    assert "a: bytes" in flatten(stub)
