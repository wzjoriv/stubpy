"""Standard-library callees and copy-with-changes idioms resolve with and without importing the project."""
from __future__ import annotations

import sys

import pytest

from tests.conftest import make_stub_ctx


def _has_signature(obj) -> bool:
    import inspect
    try:
        params = inspect.signature(obj).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.kind is not p.POSITIONAL_ONLY for p in params)


BOTH = pytest.mark.parametrize("imports", ["all", "none"])


@BOTH
@pytest.mark.skipif(not _has_signature(open), reason="this interpreter's open() takes its arguments positionally only")
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
