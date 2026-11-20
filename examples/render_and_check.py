"""Render one module without writing anything, then check a stub for staleness."""
import tempfile
from pathlib import Path

import stubpy

with tempfile.TemporaryDirectory() as folder:
    module = Path(folder) / "clock.py"
    module.write_text("def now(utc: bool = False) -> float: ...\n", encoding="utf-8")

    print(stubpy.render(module).text)

    stubpy.generate(module, Path(folder) / "stubs")
    print("fresh:", stubpy.check(module, Path(folder) / "stubs").ok)

    module.write_text("def now(utc: bool = False, tz: str = 'UTC') -> float: ...\n", encoding="utf-8")
    report = stubpy.check(module, Path(folder) / "stubs")
    print("after an edit:", report.ok, [path.name for path in report.stale])
