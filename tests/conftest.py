"""
tests/conftest.py
-----------------
Shared fixtures and utility functions used across the test suite.

Utility functions (``make_stub``, ``flatten``, ``assert_valid_syntax``) are
importable by test modules that run without pytest as well as by pytest
itself.  Pytest fixtures are defined at the bottom and silently unavailable
in non-pytest environments.
"""
from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Iterator

# Make the project root importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stubpy import generate_stub
from stubpy.context import StubContext


# ---------------------------------------------------------------------------
# Utility functions (importable everywhere)
# ---------------------------------------------------------------------------

def make_stub(source: str) -> str:
    """Write *source* to a temporary .py file, run the generator, return stub."""
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(source)
        tmp_path = Path(fh.name)
    out = tmp_path.with_suffix(".pyi")
    return generate_stub(str(tmp_path), str(out))


def flatten(content: str) -> str:
    """Collapse multi-line method signatures into a single line.

    Turns::

        def foo(
            self,
            x: int,
        ) -> None: ...

    Into::

        def foo(self, x: int,) -> None: ...
    """
    lines = content.splitlines()
    out: list[str] = []
    buf: list[str] = []
    for line in lines:
        if buf:
            stripped = line.strip()
            if stripped.startswith(")"):
                combined = buf[0] + ", ".join(buf[1:]) + stripped
                out.append(combined)
                buf = []
            else:
                buf.append(stripped)
        elif line.rstrip().endswith("("):
            buf.append(line.rstrip())
        else:
            out.append(line)
    out.extend(buf)
    return "\n".join(out)


def assert_valid_syntax(content: str) -> None:
    """Assert that *content* is parseable as valid Python."""
    try:
        ast.parse(content)
    except SyntaxError as exc:
        raise AssertionError(f"Generated stub has invalid syntax: {exc}") from exc


# ---------------------------------------------------------------------------
# Pytest fixtures (only defined when pytest is available)
# ---------------------------------------------------------------------------

try:
    import pytest  # noqa: F401 — only needed for the decorator

    @pytest.fixture
    def empty_ctx() -> StubContext:
        """A fresh, empty StubContext."""
        return StubContext()

    @pytest.fixture
    def demo_dir() -> Path:
        """Path to the demo/ package directory."""
        return ROOT / "demo"

    @pytest.fixture
    def element_stub(demo_dir: Path, tmp_path: Path) -> str:
        """Generated stub content for demo/element.py."""
        out = tmp_path / "element.pyi"
        return generate_stub(str(demo_dir / "element.py"), str(out))

    @pytest.fixture
    def container_stub(demo_dir: Path, tmp_path: Path) -> str:
        """Generated stub content for demo/container.py."""
        out = tmp_path / "container.pyi"
        return generate_stub(str(demo_dir / "container.py"), str(out))

    @pytest.fixture
    def graphics_stub(demo_dir: Path, tmp_path: Path) -> str:
        """Generated stub content for demo/graphics.py."""
        out = tmp_path / "graphics.pyi"
        return generate_stub(str(demo_dir / "graphics.py"), str(out))

except ImportError:
    pass  # pytest not installed — fixtures are unavailable, utilities still work
