"""
Read the ``[tool.stubpy]`` table of a ``pyproject.toml`` and use it to generate.
"""
# %%
import os
import tempfile
from pathlib import Path

import stubpy

TEMP = tempfile.TemporaryDirectory()
WORK = Path(os.environ.get("STUBPY_EXAMPLES_OUT") or TEMP.name)

# %%
(WORK / "pyproject.toml").write_text(
    '[tool.stubpy]\ntargets = ["src/mypkg"]\noutput_dir = "stubs"\ninclude_private = true\n',
    encoding="utf-8",
)
(WORK / "src" / "mypkg").mkdir(parents=True, exist_ok=True)
(WORK / "src" / "mypkg" / "__init__.py").write_text(
    "def _helper(x: int) -> int: ...\n\n\ndef api(x: int) -> int: ...\n", encoding="utf-8"
)

# %%
config = stubpy.load_config(WORK)
print("targets:", [Path(target).name for target in config.targets])
print("output_dir:", Path(config.output_dir).name)
print("include_private:", config.include_private)

# %%
report = stubpy.generate(config=config)
print(report.summary())
print((Path(config.output_dir) / "mypkg" / "__init__.pyi").read_text(encoding="utf-8"))
