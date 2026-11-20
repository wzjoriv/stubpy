"""Describe a JIT or compiled callable to stubpy with ``hint.signature`` and ``hint.returns``."""
import tempfile
from pathlib import Path

import stubpy

SOURCE = '''\
from stubpy import hint


def jit(function):
    return function


@jit
@hint.signature("(x: float, y: float = 0.0) -> float")
def blend(*args):
    return args[0]


@jit
@hint.returns("list[int]")
def histogram(values, bins=10):
    return []
'''

with tempfile.TemporaryDirectory() as folder:
    module = Path(folder) / "fast.py"
    module.write_text(SOURCE, encoding="utf-8")
    print(stubpy.render(module).text)
