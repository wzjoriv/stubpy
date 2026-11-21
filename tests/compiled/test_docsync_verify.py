"""``stubpy docstrings verify``: a hand-written stub compared with its module."""
from __future__ import annotations

import types

from stubpy.cli import main
from stubpy.compiled.docsync import verify_stub


def _builtin(fn, text: str):
    fn.__text_signature__ = text
    return fn


def _module() -> types.ModuleType:
    module = types.ModuleType("native")

    class Box:
        def area(self, scale): ...

        def grow(self, by): ...

    module.Box = Box
    module.make = _builtin(lambda size, fill: None, "(size, fill)")
    module.scale = _builtin(lambda x: None, "($module, x, /)")
    module.LEVEL = 3
    module.extra = _builtin(lambda: None, "()")
    return module


STUB = """\
from typing import TypeAlias

Handle: TypeAlias = int
Number = int | float
LEVEL: int

class Box:
    def area(self, scale: float) -> float: ...

def make(size: int) -> None: ...
def scale(value: float, /) -> float: ...
def gone() -> None: ...
"""


def test_differences(tmp_path):
    stub = tmp_path / "native.pyi"
    stub.write_text(STUB)
    assert sorted(verify_stub(stub, _module())) == [
        "make: stub (size), module (size, fill)",
        "missing from stub: Box.grow",
        "missing from stub: extra",
        "not in module: gone",
    ]


def test_cli_exit_code(tmp_path, monkeypatch, capsys):
    import sys

    stub = tmp_path / "native.pyi"
    stub.write_text("LEVEL: int\n")
    monkeypatch.setitem(sys.modules, "native", types.SimpleNamespace(__name__="native", LEVEL=3, __file__=None))
    monkeypatch.chdir(tmp_path)
    assert main(["docstrings", "verify", str(stub), "-m", "native", "--no-config"]) == 0
    assert "0 differ" in capsys.readouterr().out
