"""
Generate the stubs of a whole package into an output folder and read the report.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name)

# %%
package = WORK / "shapes"
(package / "tools").mkdir(parents=True, exist_ok=True)
(package / "__init__.py").write_text("from .tools import area as area\n", encoding="utf-8")
(package / "tools" / "__init__.py").write_text(
    "def area(width: float, height: float = 1.0) -> float:\n    return width * height\n", encoding="utf-8"
)

# %%
report = stubpy.generate(package, WORK / "stubs")
print(report.summary())
for path in report.written:
    print(path.relative_to(WORK / "stubs").as_posix())

# %%
print((WORK / "stubs" / "shapes" / "tools" / "__init__.pyi").read_text(encoding="utf-8"))
