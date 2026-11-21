"""A plain-text writer that subclasses the package's ``Writer`` under the same name."""
from __future__ import annotations

from typing import TypedDict

from drawlib import io


class Writer(io.Writer):
    """Writes each element as one line of text."""

    def line_width(self) -> int:
        return 80


Capabilities = TypedDict("Capabilities", {"line width": int, "wraps": bool})
