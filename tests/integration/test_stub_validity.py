"""
Stub constructs a type checker rejected: qualified TypeVars, dropped imports, names siblings import, bare ``Final``.
"""
from __future__ import annotations

import ast

import pytest

import stubpy
from stubpy import Config
from tests.conftest import write_tree

PACKAGE = {
    "vpkg/__init__.py": "",
    "vpkg/kinds.py": '''\
        import enum
        import typing as t
        from typing import Final, Optional, Union

        __all__ = ["Base", "TABLE", "define", "wrap"]

        P = t.ParamSpec("P")
        R = t.TypeVar("R")
        Mode: t.TypeAlias = t.Literal["a", "b"]
        Options = Union[int, str]
        Handler = t.Callable[[Union[str, "Base"]], "Base"]
        LIMIT = 3
        TABLE: Final = {1: "one"}


        class _Missing(enum.Enum):
            MISSING = enum.auto()


        MISSING = _Missing.MISSING
        DEFAULTS = object()


        class Base:
            def __init__(self, handler: Optional["Handler"] = None) -> None:
                self.handler = handler


        def define(x: int) -> int:
            return x


        mutable = define


        class _Parser:
            pass


        def wrap(f: t.Callable[P, R]) -> t.Callable[P, R]:
            return f
    ''',
    "vpkg/use.py": '''\
        from __future__ import annotations

        from datetime import datetime
        from ctypes import Array, c_char

        from .kinds import DEFAULTS, LIMIT, MISSING, Base, Mode, Options, _Parser, mutable


        def stamp(when: datetime, mode: Mode, opts: Options) -> Array[c_char]: ...


        def parse(parser: _Parser, limit: int = LIMIT) -> None: ...


        def build(*args, **kwargs):
            return Base(*args, **kwargs)
    ''',
}


@pytest.fixture(params=["all", "none"])
def stubs(request, tmp_path) -> dict[str, str]:
    root = write_tree(tmp_path / "src", PACKAGE)
    report = stubpy.generate(root / "vpkg", tmp_path / "out", config=Config(imports=request.param))
    assert report.ok, [d for r in report for d in r.diagnostics]
    out = tmp_path / "out" / "vpkg"
    return {name: (out / f"{name}.pyi").read_text(encoding="utf-8") for name in ("kinds", "use")}


def _names(text: str) -> set[str]:
    return {
        a.asname or a.name for n in ast.parse(text).body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
    }


def test_module_qualified_typevars_and_aliases_are_declared(stubs):
    kinds = stubs["kinds"]
    assert "P = t.ParamSpec('P')" in kinds or 'P = t.ParamSpec("P")' in kinds
    assert "R = t.TypeVar(" in kinds
    assert "Mode: TypeAlias = t.Literal[" in kinds


def test_names_another_module_imports_stay_outside_all(stubs):
    kinds = stubs["kinds"]
    for name in ("Mode", "Options", "_Parser", "LIMIT: int"):
        assert name in kinds
    assert "mutable = define" in kinds


def test_untyped_enum_member_and_imported_object(stubs):
    kinds = stubs["kinds"]
    assert "MISSING: _Missing" in kinds
    assert "DEFAULTS: " in kinds


def test_bare_final_keeps_an_initializer(stubs):
    assert "TABLE: Final = ..." in stubs["kinds"]


def test_lowercase_and_private_imported_names_are_imported(stubs):
    names = _names(stubs["use"])
    assert {"datetime", "c_char", "Array", "_Parser"} <= names


def test_quoted_alias_of_a_forwarded_parameter_is_imported(stubs):
    use = stubs["use"]
    assert "handler:" in use
    assert "Handler" in _names(use) or "Handler" not in use


def test_qualified_annotations_are_recognised_as_aliases():
    from stubpy.analysis.harvest import ast_harvest
    decls = ast_harvest("import typing as t\nV = t.TypeVar('V')\nA: t.TypeAlias = int\n").typevar_decls
    assert [(d.name, d.kind) for d in decls] == [("V", "TypeVar"), ("A", "TypeAlias")]


def test_names_inside_quoted_annotations_are_bound_but_not_literal_strings():
    from stubpy.emit._static import names_in
    assert names_in("Optional['Handler']") == ["Optional", "Handler"]
    assert names_in("Literal['sys', 'fd']") == ["Literal"]


def test_object_used_as_annotation_is_dropped_not_written_as_its_repr():
    from stubpy.emit.annotations import annotation_to_str
    from stubpy.state.context import StubContext
    assert annotation_to_str(len, StubContext()) == ""


def test_forwarded_default_naming_an_unexported_constant_is_dropped(tmp_path):
    write_tree(tmp_path / "src", {
        "fpkg/__init__.py": "",
        "fpkg/base.py": '''\
            __all__ = ["Base"]

            VERSION = "1.1"


            class Base:
                def __init__(self, version: str = VERSION, **kwargs) -> None:
                    pass
        ''',
        "fpkg/child.py": '''\
            from .base import Base

            __all__ = ["Child"]


            class Child(Base):
                def __init__(self, **kwargs) -> None:
                    super().__init__(**kwargs)
        ''',
    })
    stubpy.generate(str(tmp_path / "src"), str(tmp_path / "out"), config=Config(imports="none"))
    text = (tmp_path / "out" / "fpkg" / "child.pyi").read_text(encoding="utf-8")
    assert "VERSION" not in text
    assert "version: str = ..." in text
