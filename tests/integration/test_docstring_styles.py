"""--infer-types on NumPy, Google and Sphinx docstrings, with and without importing the module."""
from __future__ import annotations

from pathlib import Path

import pytest

from stubpy import Config, render

HERE = Path(__file__).parent / "docstyles"
SOURCE = HERE / "styles.py"


def test_live_matches_golden():
    text = render(SOURCE, config=Config(infer_types=True)).text
    assert text == (HERE / "styles.pyi.expected").read_text(encoding="utf-8")


@pytest.mark.parametrize("line", [
    "    x: int,\n    y: int,",
    "    names: list[str] | None = None,",
    ") -> tuple[int, int]: ...",
    "    path: str,",
    "    **kwargs: Any,",
    ") -> bool: ...",
    "def g_yield(n: int) -> Iterator[int]: ...",
    "def s_dict(m: dict[str, int]) -> list[str]: ...",
    "    def area(self, scale: float) -> float: ...",
])
def test_without_imports(line):
    assert line in render(SOURCE, config=Config(infer_types=True, imports="none")).text


def test_off_by_default():
    text = render(SOURCE, config=Config(imports="none")).text
    assert "def g_yield(n): ..." in text
    assert "def area(self, scale): ..." in text
