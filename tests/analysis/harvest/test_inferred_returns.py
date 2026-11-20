"""
Safe return inference from unannotated function bodies.
"""
from __future__ import annotations

import textwrap

import pytest

from stubpy.analysis.harvest import ast_harvest


def _returns(src: str) -> tuple[str | None, str | None]:
    info = ast_harvest(textwrap.dedent(src)).functions[0]
    return info.raw_inferred_return, info.inferred_return_class


@pytest.mark.parametrize(("body", "expected"), [
    ("return 1", "int"),
    ("if x:\n        return 'a'\n    return 'b'", "str"),
    ("return f'{x}'", "str"),
    ("return ', '.join(x)", "str"),
    ("return 'abc'.startswith(x)", "bool"),
    ("return len(x)", "int"),
    ("return repr(x)", "str"),
    ("return isinstance(x, int)", "bool"),
    ("return x is None", "bool"),
    ("return x in (1, 2)", "bool"),
    ("return not x", "bool"),
    ("x.append(1)", "None"),
    ("return", "None"),
])
def test_certain_returns(body, expected):
    assert _returns(f"def f(x):\n    {body}\n") == (expected, None)


@pytest.mark.parametrize("body", [
    "return x",
    "return x == 1",
    "return x < 1",
    "return x.upper()",
    "if x:\n        return 1\n    return 'a'",
    "if x:\n        return 1",
    "if x:\n        return 1\n    return",
    "len = str\n    return len(x)",
    "yield 1",
    "...",
    "raise ValueError(x)",
])
def test_uncertain_returns_are_not_inferred(body):
    assert _returns(f"def f(x):\n    {body}\n") == (None, None)


def test_self_and_class_calls():
    assert _returns("def f(self):\n    return self\n") == ("Self", None)
    assert _returns("def f(cls):\n    return cls()\n") == ("Self", None)
    assert _returns("def f(self):\n    return type(self)()\n") == ("Self", None)
    assert _returns("def f(x):\n    return Thing(x)\n") == ("Thing", "Thing")
    assert _returns("def f(x):\n    return make(x)\n") == (None, None)


def test_decorators_that_may_change_the_return_block_inference():
    assert _returns("@wrap\ndef f(x):\n    return 1\n") == (None, None)
    assert _returns("@staticmethod\ndef f(x):\n    return 1\n") == ("int", None)


def test_annotated_functions_are_left_alone():
    assert _returns("def f(x) -> object:\n    return 1\n") == (None, None)
