"""``switch`` conditional processing: ``requiredFeatures``, ``requiredExtensions`` and ``systemLanguage``."""
from __future__ import annotations

import locale
import os

FEATURE_PREFIX = "http://www.w3.org/TR/SVG11/feature#"
UNSUPPORTED_FEATURES = frozenset({
    "Script", "Cursor", "Hyperlinking", "XlinkAttribute", "ExternalResourcesRequired", "View",
    "GraphicalEventsAttribute", "DocumentEventsAttribute", "AnimationEventsAttribute", "Extensibility",
})
LANGUAGE_ENV = "SVGRASTER_LANG"
DEFAULT_LANGUAGE = "en"


def user_languages() -> list[str]:
    """Preferred languages: ``SVGRASTER_LANG``, then the locale, then English."""
    raw = os.environ.get(LANGUAGE_ENV) or (locale.getlocale()[0] or "") or DEFAULT_LANGUAGE
    langs = [part.strip().replace("_", "-").lower() for part in raw.split(",") if part.strip()]
    return langs or [DEFAULT_LANGUAGE]


def _language_ok(value: str) -> bool:
    wanted = [v.strip().lower() for v in value.split(",") if v.strip()]
    for lang in user_languages():
        primary = lang.split("-")[0]
        if any(w == lang or w == primary or w.split("-")[0] == primary for w in wanted):
            return True
    return False


def passes_conditions(node) -> bool:
    """Whether ``node``'s conditional attributes evaluate to true."""
    features = node.get("requiredFeatures")
    if features is not None:
        names = [f.replace(FEATURE_PREFIX, "") for f in features.split()]
        if not names or any(n in UNSUPPORTED_FEATURES for n in names):
            return False
    extensions = node.get("requiredExtensions")
    if extensions is not None:
        return False
    lang = node.get("systemLanguage")
    return lang is None or _language_ok(lang)
