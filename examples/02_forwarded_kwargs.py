"""
Stub a class whose ``**kwargs`` go to its base class: the stub lists the parameters they stand for.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name).resolve()

# %%
SOURCE = '''class Shape:
    def __init__(self, color: str = "black", width: float = 1.0):
        self.color = color
        self.width = width


class Circle(Shape):
    def __init__(self, radius: float, **kwargs):
        super().__init__(**kwargs)
        self.radius = radius
'''
module = WORK / "shapes.py"
module.write_text(SOURCE, encoding="utf-8")

# %%
print(stubpy.render(module).text)
