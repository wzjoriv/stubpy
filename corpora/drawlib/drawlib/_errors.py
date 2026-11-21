"""Error classes, re-exported publicly by ``drawlib.exports``."""
from __future__ import annotations

__all__ = ["RenderError", "LayoutError"]


class RenderError(Exception):
    """Rendering failed."""


class LayoutError(RenderError):
    """A layout could not be computed."""

    def offending(self) -> str:
        return ""
