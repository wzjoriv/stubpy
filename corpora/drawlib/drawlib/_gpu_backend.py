"""An optional backend that opts out at import time with a ``BaseException``, as test runners' skips do."""
from __future__ import annotations


class BackendUnavailable(BaseException):
    """Raised at import when the GPU backend cannot run here (not an ``Exception``)."""


raise BackendUnavailable("no GPU backend on this machine")


def render(scene: object, samples: int = 4) -> bytes:
    """Render *scene* on the GPU."""
    return b""
