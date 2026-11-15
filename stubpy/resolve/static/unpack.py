"""``**kwargs: Unpack[TD]`` annotations."""
from __future__ import annotations

import re

_UNPACK_RE = re.compile(r"^(?:typing(?:_extensions)?\.)?Unpack\[\s*([\w.]+)\s*\]$")


def unpacked_typeddict(annotation: str) -> str | None:
    """Return ``TD`` for the annotation text ``Unpack[TD]``, else ``None``.

    Examples
    --------
    >>> unpacked_typeddict("Unpack[Options]"), unpacked_typeddict("int")
    ('Options', None)
    """
    match = _UNPACK_RE.match(annotation.strip())
    return match.group(1) if match else None
