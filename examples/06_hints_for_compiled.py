"""
Describe a JIT-wrapped callable to stubpy with ``hint.signature`` and ``hint.returns``.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name).resolve()

# %%
SOURCE = '''from stubpy import hint


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
module = WORK / "fast.py"
module.write_text(SOURCE, encoding="utf-8")

# %%
print(stubpy.render(module).text)
