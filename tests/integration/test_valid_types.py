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


IMPORTED_SHADOW = '''
from datetime import datetime as dt_datetime, time as dt_time


class Moment:
    @property
    def datetime(self) -> dt_datetime: ...

    def time(self) -> dt_time: ...

    def shift(self, when: dt_datetime) -> "Moment": ...
'''


def test_imported_types_shadowed_by_a_member_are_module_qualified(tmp_path):
    src = tmp_path / "moments.py"
    src.write_text(IMPORTED_SHADOW)
    generate(src, tmp_path / "out")
    stub = (tmp_path / "out" / "moments.pyi").read_text()
    assert "import datetime as _datetime" in stub
    assert "def datetime(self) -> _datetime.datetime" in stub and "def time(self) -> _datetime.time" in stub
    assert "when: _datetime.datetime" in stub


@pytest.mark.skipif(__import__("sys").version_info < (3, 11), reason="generic NamedTuple needs Python 3.11")
def test_generic_namedtuple_keeps_its_generic_base(tmp_path):
    src = tmp_path / "results.py"
    src.write_text("from typing import AnyStr, Generic, NamedTuple\n"
                   "class CaptureResult(NamedTuple, Generic[AnyStr]):\n    out: AnyStr\n    err: AnyStr\n")
    generate(src, tmp_path / "out")
    assert "class CaptureResult(NamedTuple, Generic[AnyStr]):" in (tmp_path / "out" / "results.pyi").read_text()


def test_private_implementation_module_is_replaced_by_its_public_home(monkeypatch):
    import sys
    import types

    from stubpy.emit.annotations.defaults import _public_home

    impl, public = types.ModuleType("_pyclockwork"), types.ModuleType("clockwork")
    Tick = type("Tick", (), {"__module__": "_pyclockwork"})
    impl.Tick = public.Tick = Tick
    monkeypatch.setitem(sys.modules, "_pyclockwork", impl)
    monkeypatch.setitem(sys.modules, "clockwork", public)
    assert _public_home("_pyclockwork", "Tick", Tick) == "clockwork"
    monkeypatch.setattr(public, "Tick", type("Tick", (), {}))
    assert _public_home("_pyclockwork", "Tick", Tick) == "_pyclockwork"


def test_constants_built_from_other_constants_are_typed_without_importing(tmp_path):
    src = tmp_path / "pages.py"
    src.write_text("HEADER = '<html>'\nFOOTER = '</html>'\nPAGE = HEADER + '<h1>%(title)s</h1>' + FOOTER\n"
                   "KB = 1024\nMB = KB * KB\nLABEL = f'{MB} bytes'\nSHARE = MB / 3\n")
    generate(src, tmp_path / "out", config=Config(imports="none"))
    stub = (tmp_path / "out" / "pages.pyi").read_text()
    for line in ("PAGE: str", "MB: int", "LABEL: str", "SHARE: float"):
        assert line in stub


FACTORY_FUNCTIONS = '''
def _wrapper(name, scale):
    source = f"def {name}(x, *, factor={scale!r}, verbose=False):\\n    return x * factor\\n"
    namespace = {}
    exec(source, namespace)
    function = namespace[name]
    function.__module__ = __name__
    return function


double = _wrapper("double", 2)
triple = _wrapper("triple", 3)
alias = double
__all__ = ["double", "triple"]
'''


def test_functions_a_factory_makes_are_stubbed_as_functions(tmp_path):
    src = tmp_path / "solvers.py"
    src.write_text(FACTORY_FUNCTIONS)
    generate(src, tmp_path / "out")
    stub = (tmp_path / "out" / "solvers.pyi").read_text()
    assert "def double(\n    x,\n    *,\n    factor: int = 2,\n    verbose: bool = False,\n)" in stub
    assert "def triple(" in stub and "def alias" not in stub


def test_names_a_sibling_imports_are_kept_even_when_private_or_unexported(tmp_path):
    pkg = tmp_path / "sparsey"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "_utils.py").write_text(
        "__all__ = ['upcast']\n"
        "def upcast(*args): ...\n"
        "def get_index_dtype(maxval: int = 0) -> type: ...\n"
        "def _split(text: str) -> list[str]: ...\n"
        "def unused_helper() -> None: ...\n"
    )
    (pkg / "csr.py").write_text("from ._utils import get_index_dtype, _split\n"
                                "def build(n: int) -> type:\n    return get_index_dtype(n)\n")
    generate(pkg, tmp_path / "out")
    stub = (tmp_path / "out" / "sparsey" / "_utils.pyi").read_text()
    assert "def get_index_dtype(maxval: int = 0) -> type" in stub and "def _split(text: str)" in stub
    assert "unused_helper" not in stub
