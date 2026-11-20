"""
Copy the runtime docstrings of a module into its hand-written stub.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name).resolve()
import sys

# %%
package = WORK / "docdemo"
package.mkdir(exist_ok=True)
(package / "__init__.py").write_text("", encoding="utf-8")
(package / "_native.py").write_text(
    'def scale(x, factor=2):\n    """Multiply x by factor."""\n    return x * factor\n', encoding="utf-8"
)
stub = package / "_native.pyi"
stub.write_text("def scale(x: float, factor: int = 2) -> float: ...\n", encoding="utf-8")
sys.path.insert(0, str(WORK))

# %%
synced = stubpy.sync_docstrings(stub)
print(synced.text)
