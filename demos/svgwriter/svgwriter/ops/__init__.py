"""Boolean operations backed by the optional skia-python dependency.

Install with ``pip install 'svgwriter[ops]'``. The module always imports;
each function raises :class:`MissingDependencyError` when skia-python is
missing.
"""

from __future__ import annotations

from ._skia import INSTALL_HINT, Geometry, MissingDependencyError, available, combine

__all__ = ["INSTALL_HINT", "Geometry", "MissingDependencyError", "available", "combine"]
