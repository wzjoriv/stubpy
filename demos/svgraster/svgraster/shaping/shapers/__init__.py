"""Script shapers: feature stages, masks and reordering per script, after HarfBuzz's shaping model."""
from __future__ import annotations

from ._arabic import ArabicShaper
from ._base import Plan, Shaper
from ._hebrew import HebrewShaper
from ._indic import IndicShaper
from ._thai import ThaiShaper

_SHAPERS: dict[str, Shaper] = {}
_BY_SCRIPT = {
    "Arabic": ArabicShaper, "Syriac": ArabicShaper, "Nko": ArabicShaper,
    "Devanagari": IndicShaper,
    "Hebrew": HebrewShaper,
    "Thai": ThaiShaper, "Lao": ThaiShaper,
}


def shaper_for(script: str) -> Shaper:
    """The shaper for an ISO script name (the default shaper for unlisted scripts)."""
    cls = _BY_SCRIPT.get(script, Shaper)
    found = _SHAPERS.get(cls.__name__)
    if found is None:
        found = _SHAPERS[cls.__name__] = cls()
    return found


__all__ = ["ArabicShaper", "HebrewShaper", "IndicShaper", "Plan", "Shaper", "ThaiShaper", "shaper_for"]
