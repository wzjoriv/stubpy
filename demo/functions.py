# demo/functions.py
# Exercises module-level function stub generation (P2-A)
# Covers: sync, async, type-annotated, defaults, *args, **kwargs, kw-only
from __future__ import annotations

from typing import Optional, List

__all__ = [
    "greet",
    "add",
    "fetch_data",
    "process",
    "transform",
    "make_pair",
]


def greet(name: str, *, greeting: str = "Hello") -> str:
    """Return a greeting string."""
    return f"{greeting}, {name}!"


def add(a: float, b: float = 0.0) -> float:
    """Add two numbers."""
    return a + b


async def fetch_data(url: str, timeout: float = 30.0) -> bytes:
    """Async HTTP fetch (stub only)."""
    return b""


def process(items: List[str], flag: bool = False, *args: int, **kwargs: str) -> None:
    """Process items with various param kinds."""
    pass


def transform(x: int, y: int, z: int, scale: float = 1.0) -> tuple:
    """Multi-param function (triggers multi-line stub)."""
    return (x * scale, y * scale, z * scale)


def make_pair(first: str, second: str) -> tuple:
    return (first, second)


# Private — should be excluded from stubs
def _internal_helper(x: int) -> int:
    return x * 2
