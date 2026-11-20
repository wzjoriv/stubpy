"""
Stub a Cython extension from its ``.pyx`` source, with no compiler and no build.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name)

# %%
package = WORK / "fastmath"
package.mkdir(exist_ok=True)
(package / "__init__.py").write_text("", encoding="utf-8")
(package / "_core.pyx").write_text(
    "def scale(double x, int factor=2):\n"
    "    '''Multiply x by factor.'''\n"
    "    return x * factor\n",
    encoding="utf-8",
)

# %%
report = stubpy.generate(package, WORK / "stubs")
print(report.summary())
print((WORK / "stubs" / "fastmath" / "_core.pyi").read_text(encoding="utf-8"))
