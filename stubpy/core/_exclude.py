"""Which files a folder run skips: ``exclude`` / ``extend_exclude`` patterns and the ``<non-identifier>`` rule."""
from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from stubpy._constants import NON_IDENTIFIER_RULE
from stubpy.compiled.detect import module_stem


def excluded_by(rel: str, patterns: tuple[str, ...]) -> str | None:
    """The first pattern that excludes the file at *rel* (a ``/`` path under the folder target), else ``None``.

    A pattern with a ``/`` matches the whole relative path; one without
    matches any single folder or file name on it.  ``<non-identifier>``
    matches a folder, or a module file, whose name Python cannot import.
    """
    parts = PurePosixPath(rel).parts
    for pattern in patterns:
        if pattern == NON_IDENTIFIER_RULE:
            if any(not p.isidentifier() for p in parts[:-1]) or not module_stem(parts[-1]).isidentifier():
                return pattern
        elif "/" in pattern:
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, pattern.rstrip("/") + "/*"):
                return pattern
        elif any(fnmatch.fnmatch(p, pattern) for p in parts):
            return pattern
    return None
