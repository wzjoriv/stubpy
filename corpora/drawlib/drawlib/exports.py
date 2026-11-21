"""The public face of the errors: star-imported, then relabelled to this module (as httpx does)."""
from __future__ import annotations

from ._errors import *
from ._errors import __all__ as _errors_all

__all__ = list(_errors_all)

for _name in __all__:
    globals()[_name].__module__ = __name__
