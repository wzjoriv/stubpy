"""Stub a small package whose class forwards ``**kwargs`` to its base class."""
import tempfile
from pathlib import Path

import stubpy

SOURCE = '''\
class Shape:
    def __init__(self, color: str = "black", width: float = 1.0):
        self.color = color
        self.width = width


class Circle(Shape):
    def __init__(self, radius: float, **kwargs):
        super().__init__(**kwargs)
        self.radius = radius
'''

with tempfile.TemporaryDirectory() as folder:
    package = Path(folder) / "shapes"
    package.mkdir()
    (package / "__init__.py").write_text(SOURCE, encoding="utf-8")

    report = stubpy.generate(package, Path(folder) / "stubs")
    print((Path(folder) / "stubs" / "shapes" / "__init__.pyi").read_text(encoding="utf-8"))
    print(f"ok: {report.ok}")
