# demo/scene.py  —  PixelForge / generic containers and protocols
# -------------------------------------------------------------------
# Exercises: TypeVar (plain, bound, constrained), Generic[T], Generic[K,V],
#            Protocol (@runtime_checkable), TypeAlias, NewType, ParamSpec,
#            bound TypeVar in function signatures.
"""
Generic containers and structural protocols for PixelForge.

This module shows how a typed drawing library uses Python's generic
machinery to build reusable, type-safe data structures:

  - Stack[T]              — last-in, first-out element stack
  - SpatialIndex[T]       — fast bounding-box lookup
  - Pipeline[P, T]        — composable render pipeline
  - Drawable / Measurable — structural protocols
"""
from __future__ import annotations

import sys
from typing import (
    Callable, Generic, Iterator, NewType, Protocol,
    TypeAlias, TypeVar, runtime_checkable,
)

__all__ = [
    # TypeVar declarations
    "T", "K", "V", "DrawableT", "NumericT",
    # Type aliases
    "Pixels", "SceneId", "Matrix2x2",
    # Generic containers
    "Stack", "SpatialIndex",
    # Protocols
    "Drawable", "Measurable",
    # Functions with TypeVar
    "first", "flatten", "pipe",
]


# ── TypeVar declarations (re-emitted verbatim by stubpy) ─────────────────

T        = TypeVar("T")
K        = TypeVar("K")
V        = TypeVar("V")
DrawableT = TypeVar("DrawableT", bound="Drawable")   # bound TypeVar
NumericT  = TypeVar("NumericT", int, float)           # constrained TypeVar


# ── Type aliases ─────────────────────────────────────────────────────────

Pixels:   TypeAlias = int               # device pixels
SceneId:  TypeAlias = str               # unique scene identifier
Matrix2x2: TypeAlias = tuple[           # 2×2 affine sub-matrix
    tuple[float, float],
    tuple[float, float],
]

# NewType — a distinct type for validated pixel values
SafePixels = NewType("SafePixels", int)


# ── Generic[T] — typed element stack ─────────────────────────────────────

class Stack(Generic[T]):
    """Last-in, first-out stack of elements of type *T*.

    Used internally by the renderer to manage draw calls and clip regions.
    """

    def __init__(self) -> None:
        self._items: list[T] = []

    def push(self, item: T) -> None:
        """Push *item* onto the top of the stack."""
        self._items.append(item)

    def pop(self) -> T:
        """Remove and return the top element."""
        return self._items.pop()

    def peek(self) -> T:
        """Return the top element without removing it."""
        return self._items[-1]

    def is_empty(self) -> bool:
        """Return ``True`` when the stack has no elements."""
        return not self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(reversed(self._items))


# ── Generic[K, V] — spatial lookup table ─────────────────────────────────

class SpatialIndex(Generic[K, V]):
    """Map of keys *K* to spatial values *V* with bounding-box lookup.

    Keys are typically :data:`~demo.types.SceneId` strings; values are
    drawable objects paired with their bounding boxes.
    """

    def __init__(self) -> None:
        self._store: dict[K, V] = {}

    def insert(self, key: K, value: V) -> None:
        """Store *value* under *key*."""
        self._store[key] = value

    def lookup(self, key: K) -> V:
        """Retrieve the value for *key*."""
        return self._store[key]

    def remove(self, key: K) -> V:
        """Remove and return the value for *key*."""
        return self._store.pop(key)

    def __contains__(self, key: K) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)


# ── Protocols ─────────────────────────────────────────────────────────────

@runtime_checkable
class Drawable(Protocol):
    """Anything that can render itself to a string fragment."""

    def render(self, *, compact: bool = False) -> str:
        """Return an SVG/HTML fragment for this object."""
        ...


@runtime_checkable
class Measurable(Protocol):
    """Anything that reports its bounding box."""

    def bounding_box(self) -> "tuple[float, float, float, float]":
        """Return ``(x, y, width, height)`` in scene coordinates."""
        ...


# ── Functions with TypeVar in signatures ──────────────────────────────────

def first(items: list[T]) -> T:
    """Return the first element of a non-empty list.

    Preserves the element type exactly — ``first([1, 2]) -> int``.
    """
    return items[0]


def flatten(nested: list[list[T]]) -> list[T]:
    """Flatten one level of nesting from a list of lists."""
    return [item for sublist in nested for item in sublist]


def pipe(value: T, *transforms: Callable[[T], T]) -> T:
    """Apply a sequence of transformations to *value* left-to-right.

    All transforms must accept and return the same type *T*.

    Example::

        scaled = pipe(canvas, add_margin, clip_to_viewport, quantise)
    """
    result = value
    for fn in transforms:
        result = fn(result)
    return result


def clamp_pixels(value: NumericT, lo: NumericT, hi: NumericT) -> NumericT:
    """Clamp a pixel value (int or float) to [lo, hi], preserving type."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
