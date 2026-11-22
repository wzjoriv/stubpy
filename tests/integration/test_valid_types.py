"""Stub annotations type checkers accept: implicit aliases with any-case names, ``Annotated`` with real metadata."""
from __future__ import annotations

import pytest

from stubpy import Config, generate
from stubpy.analysis.harvest import ast_harvest

ALIASES = '''
from typing import Iterable, Mapping, Union
from datetime import tzinfo as dt_tzinfo
from email.message import Message as msg

TZ_EXPR = Union[dt_tzinfo, str]
LooseHeaders = Union[Mapping[str, str], Mapping[msg, str], Iterable[tuple[str | msg, str]]]
picked = table[key]
mask = flags[a | b]
'''


def test_known_type_subscripts_accept_any_case_names():
    harvested = ast_harvest(ALIASES.replace("table[key]", "{}['k']").replace("flags[a | b]", "{}[1 | 2]"))
    assert {t.name for t in harvested.typevar_decls} == {"TZ_EXPR", "LooseHeaders"}
    assert {v.name for v in harvested.variables} == {"picked", "mask"}


ANNOTATED = '''
from typing import Annotated, Any


class Doc:
    def __init__(self, text):
        self.text = text


class Event:
    data: Annotated[Any, Doc("payload")]
    raw: Annotated[str | None, Doc("raw")] = None
    size: Annotated[int, "bytes"] = 0
'''


@pytest.mark.parametrize("imports", ["all"])
def test_annotated_keeps_only_literal_metadata(tmp_path, imports):
    src = tmp_path / "events.py"
    src.write_text(ANNOTATED)
    generate(src, tmp_path / "out", config=Config(imports=imports))
    body = (tmp_path / "out" / "events.pyi").read_text().split("class Event:")[1]
    assert "    data: Any\n" in body and "    raw: str | None\n" in body
    assert "    size: Annotated[int, 'bytes']\n" in body


SHADOWING = '''
from typing import Any


class Model:
    def dict(self, include: set[str] | None = None) -> dict[str, Any]:
        return {}

    def add(self, filter, dict=None) -> None: ...


def plain(d: dict) -> set[str]: ...
'''


def test_builtins_shadowed_by_a_member_are_qualified_inside_the_class(tmp_path):
    src = tmp_path / "models.py"
    src.write_text(SHADOWING)
    generate(src, tmp_path / "out")
    stub = (tmp_path / "out" / "models.pyi").read_text()
    assert "import builtins" in stub
    assert "-> builtins.dict[str, Any]" in stub and "def add(self, filter, dict=None)" in stub
    assert "def plain(d: dict) -> set[str]" in stub
