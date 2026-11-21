"""Header imports for names only a defaulted annotation uses, and for plain imports that share a last segment."""
from __future__ import annotations

import pytest

from stubpy import Config, generate

SOURCE = '''
from __future__ import annotations
from datetime import time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from datetime import timedelta
    import unittest
    import xml.dom.minidom


def span(start: time, interval: str | timedelta = "1h") -> None: ...
def case(c: unittest.TestCase, node: xml.dom.minidom.Node) -> None: ...
'''


@pytest.mark.parametrize("imports", ["all", "none"])
def test_header_imports(tmp_path, imports):
    src = tmp_path / "ranges.py"
    src.write_text(SOURCE)
    generate(src, tmp_path / "out", config=Config(imports=imports))
    header = (tmp_path / "out" / "ranges.pyi").read_text().split("\ndef ")[0]
    assert "from datetime import time, timedelta" in header
    assert "import unittest\n" in header and "import xml.dom.minidom" in header
