"""Basic shapes and ``<path>``.

Modules
-------
_basic   ``Shape`` and rect, circle, line
_path    path
"""

from __future__ import annotations

from ._basic import Circle, Line, Rect, Shape
from ._path import Path

__all__ = ["Circle", "Line", "Path", "Rect", "Shape"]
