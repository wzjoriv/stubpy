"""Read the ``[tool.stubpy]`` table of a ``pyproject.toml`` with ``stubpy.load_config``."""
import tempfile
from pathlib import Path

import stubpy

PYPROJECT = """\
[tool.stubpy]
targets = ["src/mypkg"]
output_dir = "stubs"
include_private = true
"""

with tempfile.TemporaryDirectory() as folder:
    (Path(folder) / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")

    config = stubpy.load_config(folder)
    print("targets:", [Path(target).name for target in config.targets])
    print("output_dir:", Path(config.output_dir).name)
    print("include_private:", config.include_private)
