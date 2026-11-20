"""Standard-library callees and copy-with-changes idioms resolve with and without importing the project."""
from __future__ import annotations

import re
import sys

import pytest

from tests.conftest import make_stub_ctx

BOTH = pytest.mark.parametrize("imports", ["all", "none"])


@BOTH
def test_builtin_open_inside_with(imports):
    stub, _ = make_stub_ctx("""
        def atomic_write(path, mode="w", **kwargs):
            with open(path + ".part", mode, **kwargs) as fh:
                return fh
    """, imports=imports)
    sig = stub.split("def atomic_write(")[1]
    for name in ("buffering", "encoding", "errors", "newline", "closefd", "opener"):
        assert f"{name}" in sig
    assert "**kwargs" not in sig and "file" not in sig


@BOTH
def test_stdlib_functions(imports):
    stub, _ = make_stub_ctx("""
        import json
        import subprocess

        def run(cmd: list[str], **kwargs):
            return subprocess.run(cmd, **kwargs)

        def dumps(obj, **kwargs) -> str:
            return json.dumps(obj, **kwargs)
    """, imports=imports)
    assert "check: bool = False," in stub.split("def run(")[1].split("def dumps")[0]
    assert "sort_keys: bool = False," in stub.split("def dumps(")[1]


@BOTH
def test_stdlib_method_through_a_typed_attribute(imports):
    stub, _ = make_stub_ctx("""
        import logging

        class Log:
            def __init__(self, logger: logging.Logger) -> None:
                self.logger = logger

            def log(self, level: int, msg: str, *args, **kwargs) -> None:
                self.logger.log(level, msg, *args, **kwargs)
    """, imports=imports)
    log = stub.split("def log(")[1]
    assert "exc_info=None," in log and "stacklevel" in log and "**kwargs" not in log


@BOTH
def test_untyped_attribute_call_is_not_misresolved(imports):
    stub, _ = make_stub_ctx("""
        def draw(*, colour: str = "red") -> None: ...

        class View:
            def __init__(self, impl) -> None:
                self.impl = impl

            def draw(self, **kwargs) -> None:
                self.impl.draw(**kwargs)
    """, imports=imports)
    assert "def draw(self, **kwargs) -> None: ..." in stub


COPY_SOURCE = """
    import copy
    import dataclasses
    from dataclasses import dataclass, field
    from typing import NamedTuple

    @dataclass
    class Point:
        x: int
        y: int = 0
        tag: str = field(default="", init=False)

        def with_(self, **changes) -> "Point":
            return dataclasses.replace(self, **changes)

        def but_x(self, **changes) -> "Point":
            return dataclasses.replace(self, x=1, **changes)

    def move(p: Point, **changes) -> Point:
        return dataclasses.replace(p, **changes)

    class Pair(NamedTuple):
        a: int
        b: str = ""

        def but(self, **changes) -> "Pair":
            return self._replace(**changes)

    def swap(pair: "Pair", **changes) -> Pair:
        return pair._replace(**changes)
"""

FIELDS = "    *,\n    x: int = ...,\n    y: int = ...,\n)"


@BOTH
def test_dataclass_replace(imports):
    stub, _ = make_stub_ctx(COPY_SOURCE, imports=imports)
    assert "def with_(\n        self,\n        *,\n        x: int = ...,\n        y: int = ...,\n    ) -> Point" in stub
    assert "tag" not in stub.split("def with_(")[1].split(")")[0]
    assert "def but_x(self, *, y: int = ...) -> Point" in stub
    assert f"def move(\n    p: Point,\n{FIELDS} -> Point" in stub


@BOTH
def test_namedtuple_replace(imports):
    stub, _ = make_stub_ctx(COPY_SOURCE, imports=imports)
    assert "def but(\n        self,\n        *,\n        a: int = ...,\n        b: str = ...,\n    ) -> Pair" in stub
    assert "def swap(\n    pair: Pair,\n    *,\n    a: int = ...,\n    b: str = ...,\n) -> Pair" in stub


@pytest.mark.skipif(sys.version_info < (3, 13), reason="copy.replace needs Python 3.13")
@BOTH
def test_copy_replace(imports):
    stub, _ = make_stub_ctx("""
        import copy
        from dataclasses import dataclass

        @dataclass
        class Size:
            w: float
            h: float = 1.0

            def resized(self, **changes) -> "Size":
                return copy.replace(self, **changes)
    """, imports=imports)
    assert "w: float = ...," in stub.split("def resized(")[1] and "h: float = ...," in stub.split("def resized(")[1]


@BOTH
def test_open_keywords_are_typed(imports):
    stub, _ = make_stub_ctx("""
        def read(path, **kwargs):
            with open(path, "r", **kwargs) as fh:
                return fh.read()
    """, imports=imports)
    sig = stub.split("def read(")[1]
    for text in ("encoding: str | None = None", "errors: str | None = None", "newline: str | None = None",
                 "opener: Callable[[str, int], int] | None = None", "closefd: bool = True"):
        assert text in sig
    assert "from collections.abc import Callable" in stub


@BOTH
def test_io_open_alias_is_expanded(imports):
    stub, _ = make_stub_ctx("""
        import io

        def read(path, **kwargs):
            return io.open(path, **kwargs)
    """, imports=imports)
    assert "encoding: str | None = None" in stub and "**kwargs" not in stub


@BOTH
def test_unknown_callee_keeps_kwargs(imports):
    stub, _ = make_stub_ctx("""
        import missing_lib

        def call(**kwargs):
            return missing_lib.run(**kwargs)
    """, imports=imports)
    assert "**kwargs" in stub


@BOTH
def test_bare_replace_expands_into_fields(imports):
    stub, _ = make_stub_ctx("""
        from dataclasses import dataclass, replace
        from typing import Any

        @dataclass
        class Box:
            width: int = 1
            label: str = ""

            def variant(self, **changes: Any) -> "Box":
                return replace(self, **changes)
    """, imports=imports)
    variant = stub.split("def variant(")[1]
    assert "width: int = ..." in variant and "label: str = ..." in variant and "**changes" not in variant


@BOTH
def test_aliased_copy_function_expands_into_fields(imports):
    stub, _ = make_stub_ctx("""
        from dataclasses import dataclass, replace as copy_with

        @dataclass
        class Box:
            width: int = 1

            def variant(self, **changes) -> "Box":
                return copy_with(self, **changes)
    """, imports=imports)
    assert "width: int = ..." in stub.split("def variant(")[1]


@BOTH
def test_own_replace_function_is_not_a_copy(imports):
    stub, _ = make_stub_ctx("""
        from dataclasses import dataclass

        def replace(obj, **options):
            return obj

        @dataclass
        class Box:
            width: int = 1

            def variant(self, **changes) -> "Box":
                return replace(self, **changes)
    """, imports=imports)
    assert "width: int = ..." not in stub.split("def variant(")[1]


def test_string_replace_is_not_a_copy():
    stub, _ = make_stub_ctx("""
        class Name:
            def fix(self, **kw):
                return self.replace("a", "b", **kw)
    """)
    assert "**kw" in stub


@BOTH
def test_or_fallback_takes_the_constructed_type(imports):
    stub, _ = make_stub_ctx("""
        class Theme: ...

        class Holder:
            def __init__(self, theme: Theme | None = None, label: str | None = None, size: int = 0):
                self.theme = theme or Theme()
                self.label = label or "x"
                self.size = size or 3
                self.other = unknown() or Theme()
    """, imports=imports)
    body = stub.split("class Holder:")[1]
    assert re.search(r"^    theme: Theme$", body, re.M) and re.search(r"^    label: str$", body, re.M)
    assert re.search(r"^    size: int$", body, re.M) and "other: Theme" not in body
