"""
Check whether the written stubs still match their source: the test to run in CI.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name).resolve()

# %%
module = WORK / "clock.py"
module.write_text("def now(utc: bool = False) -> float: ...\n", encoding="utf-8")
stubpy.generate(module, WORK / "stubs")
report = stubpy.check(module, WORK / "stubs")
print(report.summary())

# %%
module.write_text("def now(utc: bool = False, tz: str = 'UTC') -> float: ...\n", encoding="utf-8")
report = stubpy.check(module, WORK / "stubs")
print(report.summary())
print("stale:", [path.name for path in report.stale])
