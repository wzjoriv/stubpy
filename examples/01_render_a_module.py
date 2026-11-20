"""
Render the stub of one module without writing anything.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name)

# %%
module = WORK / "clock.py"
module.write_text(
    "import time\n\n\n"
    "def now(utc: bool = False) -> float:\n"
    "    return time.time()\n\n\n"
    "class Timer:\n"
    "    running = False\n\n"
    "    def start(self, label='timer'):\n"
    "        self.running = True\n",
    encoding="utf-8",
)

# %%
result = stubpy.render(module)
print(result.text)
print("ok:", result.ok)
