"""Unannotated class attributes holding instances: one field each, never also a method; ``type`` aliases are local."""
from __future__ import annotations

import sys
import textwrap

import pytest

from stubpy import Config, generate

SETTINGS = '''
class Setting:
    def __init__(self, name):
        self.name = name
    def __call__(self, value=None):
        return value
    def __get__(self, instance, owner) -> "Setting":
        return self


class Plain:
    pass


class Settings:
    origin: Setting = Setting("origin")
    other = Setting("other")
    marker = Plain()
'''


def test_callable_descriptor_is_a_field_not_a_method(tmp_path):
    src = tmp_path / "settings.py"
    src.write_text(textwrap.dedent(SETTINGS))
    generate(src, tmp_path / "out")
    body = (tmp_path / "out" / "settings.pyi").read_text().split("class Settings:")[1]
    assert "def origin" not in body and "def other" not in body
    assert "    origin: Setting\n" in body and "    other: Setting\n" in body
    assert "    marker: Plain\n" in body


LAZY = '''
class Lazy:
    """Sets itself up on any attribute access, ``__class__`` included, and cannot here (like Django's LazyObject)."""
    def __getattribute__(self, name):
        raise RuntimeError("settings are not configured")


class Finder:
    storage = Lazy()

    def find(self, path: str) -> str: ...
'''


def test_lazy_proxy_attribute_is_never_touched(tmp_path):
    src = tmp_path / "finders.py"
    src.write_text(textwrap.dedent(LAZY))
    report = generate(src, tmp_path / "out")
    body = (tmp_path / "out" / "finders.pyi").read_text().split("class Finder:")[1]
    assert "    storage: Lazy\n" in body and "def find(self, path: str) -> str" in body
    assert not [d for r in report.results for d in r.diagnostics if "emission failed" in d.message]


@pytest.mark.skipif(sys.version_info < (3, 12), reason="type statements need Python 3.12")
@pytest.mark.parametrize("imports", ["all", "none"])
def test_type_statement_name_is_not_imported(tmp_path, imports):
    src = tmp_path / "aliases.py"
    src.write_text('__all__ = ["NotRequired"]\ntype NotRequired[T] = int | T\n')
    generate(src, tmp_path / "out", config=Config(imports=imports))
    stub = (tmp_path / "out" / "aliases.pyi").read_text()
    assert "import" not in stub and "type NotRequired[T] = int | T" in stub


UNNAMEABLE = '''
def lazy(value):
    class __proxy__:
        pass
    return __proxy__()


class Typed:
    def __set__(self, instance, value):
        instance.__dict__["x"] = value


class Constraint:
    message = lazy("violated")
    width = Typed()
'''


def test_unnameable_and_set_only_descriptor_values_get_no_field(tmp_path):
    src = tmp_path / "constraints.py"
    src.write_text(textwrap.dedent(UNNAMEABLE))
    generate(src, tmp_path / "out")
    body = (tmp_path / "out" / "constraints.pyi").read_text().split("class Constraint:")[1]
    assert "__proxy__" not in body and "width: Typed" not in body


@pytest.mark.parametrize("imports", ["all", "none"])
def test_bare_final_keeps_a_short_literal_value(tmp_path, imports):
    src = tmp_path / "nodes.py"
    src.write_text(
        "from typing import Final\n"
        "def compute(): return 1\n"
        "class Node:\n    tagname: str\n"
        "class Text(Node):\n    tagname: Final = '#text'\n    children: Final = ()\n    big: Final = compute()\n"
    )
    generate(src, tmp_path / "out", config=Config(imports=imports))
    body = (tmp_path / "out" / "nodes.pyi").read_text().split("class Text(Node):")[1]
    assert "tagname: Final = '#text'" in body and "children: Final = ()" in body and "big: Final = ..." in body
