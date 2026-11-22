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


def test_names_merely_imported_by_a_module_are_imported_from_their_origin(tmp_path):
    pkg = tmp_path / "rexp"
    (pkg / "core").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "core" / "__init__.py").write_text("")
    (pkg / "core" / "base.py").write_text("class Base: ...\nclass Other: ...\n")
    (pkg / "_typing.py").write_text(
        "import numpy.typing as npt\n"
        "from typing import Any as Any\n"
        "from .core.base import Base, Other\n"
        "__all__ = ['Base']\n"
    )
    (pkg / "core" / "series.py").write_text(
        "from __future__ import annotations\n"
        "from rexp._typing import npt, Any, Base, Other\n"
        "def f(a: npt.NDArray, b: Any, c: Base, d: Other) -> None: ...\n"
    )
    generate(pkg, tmp_path / "out", config=Config(imports="none"))
    header = (tmp_path / "out" / "rexp" / "core" / "series.pyi").read_text().split("\ndef ")[0]
    assert "import numpy.typing as npt" in header
    assert "from rexp._typing import Any, Base" in header
    assert "from rexp.core.base import Other" in header


@pytest.mark.parametrize("imports", ["all", "none"])
def test_module_class_alias_is_written_as_an_alias(tmp_path, imports):
    src = tmp_path / "conc.py"
    src.write_text("import asyncio\nimport collections\nFuture = asyncio.Future\nOD = collections.OrderedDict\n"
                   "def f() -> Future: ...\n")
    generate(src, tmp_path / "out", config=Config(imports=imports))
    stub = (tmp_path / "out" / "conc.pyi").read_text()
    assert "import asyncio\n" in stub and "import collections\n" in stub
    assert "Future: TypeAlias = asyncio.Future\n" in stub and "OD: TypeAlias = collections.OrderedDict\n" in stub
    assert "_asyncio" not in stub and "def f() -> Future" in stub
