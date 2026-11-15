"""Tests for stubpy.emit.decorators: the stub decorator allow-list."""
from __future__ import annotations

import pytest

from stubpy.analysis.imports import collect_decorator_imports
from stubpy.emit.decorators import decorator_base_name, stub_decorator, stub_decorators


@pytest.mark.parametrize("source, expected", [
    ("overload", "overload"),
    ("typing.overload", "overload"),
    ("abc.abstractmethod", "abstractmethod"),
    ("property", "property"),
    ("value.setter", "value.setter"),
    ("value.deleter", "value.deleter"),
    ("functools.cached_property", "cached_property"),
    ("classmethod", "classmethod"),
    ("staticmethod", "staticmethod"),
    ("typing.final", "final"),
    ("override", "override"),
    ("runtime_checkable", "runtime_checkable"),
    ("type_check_only", "type_check_only"),
    ("deprecated('use g')", "deprecated('use g')"),
    ("warnings.deprecated('x')", "deprecated('x')"),
    ("dataclass(frozen=True)", "dataclass(frozen=True)"),
    ("typing.dataclass_transform(kw_only_default=True)", "dataclass_transform(kw_only_default=True)"),
    ("contextlib.contextmanager", "contextmanager"),
    ("asynccontextmanager", "asynccontextmanager"),
    ("functools.singledispatch", "singledispatch"),
])
def test_kept_decorators(source, expected):
    assert stub_decorator(source) == expected


@pytest.mark.parametrize("source", [
    "lru_cache", "functools.lru_cache(maxsize=None)", "functools.cache", "app.route('/x')",
    "functools.wraps(f)", "pytest.fixture", "register", "Base.v.setter", "x[0]",
])
def test_dropped_decorators(source):
    assert stub_decorator(source) is None


def test_stub_decorators_keeps_order():
    assert stub_decorators(["functools.lru_cache", "staticmethod", "typing.final"]) == ["staticmethod", "final"]


def test_decorator_base_name():
    assert decorator_base_name("app.route('/')") == "route"
    assert decorator_base_name("x[0]") == ""


def test_decorator_imports():
    body = "@cached_property\ndef a(self): ...\n@deprecated('x')\ndef b(): ...\n@property\ndef c(self): ...\n"
    assert collect_decorator_imports(body) == {
        "functools": ["cached_property"],
        "typing_extensions": ["deprecated"],
    }
