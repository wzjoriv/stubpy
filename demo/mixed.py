# demo/mixed.py
# A mixed-symbol module: public API facade for the drawing library.
# Exercises: __all__ with mixed kinds, module-level functions, variables,
#            and classes that should be included or excluded.
from __future__ import annotations

from demo import types
from demo.container import Scene
from demo.element import Element

__all__ = ["DEFAULT_COLOR", "make_scene", "Canvas"]

DEFAULT_COLOR: str = "black"
INTERNAL_CONSTANT: int = 42   # not in __all__ → excluded

def make_scene(
    width:  types.Length = 800,
    height: types.Length = 600,
) -> Scene:
    """Create a blank :class:`~demo.container.Scene` with the given dimensions."""
    return Scene(width=width, height=height)

def _private_factory(width: types.Length) -> Scene:
    return Scene(width=width)

def helper_func(x: int) -> int:   # public but not in __all__ → excluded
    return x

class Canvas(Scene):
    """Convenience subclass of :class:`~demo.container.Scene` with a title."""

    def __init__(self, title: str = "Untitled", **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = title

class InternalCanvas(Canvas):   # not in __all__ → excluded
    pass
