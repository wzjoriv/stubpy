# demo/container.py
# Scene-graph container classes.
# Exercises: **kwargs backtracing through 3-level chain (Layer → Container →
#            Element), *args preservation, @property, @classmethod, async
#            generator method, private attributes, __all__.
from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Callable, Iterator, Optional, Sequence

from demo import types
from demo.element import Element

__all__ = ["Container", "Layer", "Scene"]

# Private render statistics — excluded from default stubs.
_total_renders: int = 0
_render_errors: list[str] = []


class Container(Element):
    """An element that owns and manages child elements.

    Children are stored in insertion order.  The container's bounding box
    is the union of all children's bounding boxes.
    """

    def __init__(
        self,
        *elements: Element,
        clip:     bool         = False,
        overflow: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.clip       = clip
        self.overflow   = overflow
        self._children: list[Element] = list(elements)

    # -- Child management ----------------------------------------------------

    def add(self, *elements: Element) -> Container:
        """Append one or more elements and return self (chainable)."""
        self._children.extend(elements)
        return self

    def remove(self, element: Element) -> Container:
        self._children.remove(element)
        return self

    def clear(self) -> Container:
        self._children.clear()
        return self

    def __iter__(self) -> Iterator[Element]:
        return iter(self._children)

    def __len__(self) -> int:
        return len(self._children)

    def __getitem__(self, index: int) -> Element:
        return self._children[index]

    def __contains__(self, element: object) -> bool:
        return element in self._children

    def get(self, index: int) -> Element:
        """Return the child element at *index* (alias for ``__getitem__``)."""
        return self._children[index]

    def clone(self, deep: bool = True) -> Container:
        """Return a shallow or deep copy of this container."""
        import copy
        return copy.deepcopy(self) if deep else copy.copy(self)

    # -- Async traversal -----------------------------------------------------

    async def iter_async(self) -> AsyncIterator[Element]:
        """Yield each child asynchronously for non-blocking traversals."""
        for child in self._children:
            yield child

    # -- Properties ----------------------------------------------------------

    @property
    def children(self) -> tuple[Element, ...]:
        """Snapshot of child elements as an immutable tuple."""
        return tuple(self._children)

    @property
    def bounding_box(self) -> types.BoundingBox:
        if not self._children:
            return (0.0, 0.0, 0.0, 0.0)
        boxes = [c.bounding_box for c in self._children]
        x  = min(b[0] for b in boxes)
        y  = min(b[1] for b in boxes)
        x2 = max(b[0] + b[2] for b in boxes)
        y2 = max(b[1] + b[3] for b in boxes)
        return (x, y, x2 - x, y2 - y)

    # -- Rendering -----------------------------------------------------------

    def render(self, compact: bool = False) -> str:
        sep = "" if compact else "\n"
        inner = sep.join(c.render(compact) for c in self._children)
        return f"<g>{inner}</g>"

    # -- Factories -----------------------------------------------------------

    @classmethod
    def from_elements(cls, *elements: Element, **kwargs: Any) -> Container:
        """Create a container already populated with *elements*."""
        c = cls(**kwargs)
        c.add(*elements)
        return c


class Layer(Container):
    """A named, z-ordered layer within a scene.

    Tests three-level ``**kwargs`` chain: Layer → Container → Element.
    Also exercises kw-only parameters (``label`` after the ``*`` separator).
    """

    def __init__(
        self,
        name:    str,
        z_index: int   = 0,
        locked:  bool  = False,
        visible: bool  = True,
        *,
        label:     Optional[str]                = None,
        on_change: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.name      = name
        self.z_index   = z_index
        self.locked    = locked
        self.visible   = visible
        self.label     = label
        self.on_change = on_change

    @property
    def is_locked(self) -> bool:
        return self.locked

    def lock(self) -> Layer:
        """Lock this layer so it cannot be edited."""
        self.locked = True
        return self

    def unlock(self) -> Layer:
        """Unlock this layer."""
        self.locked = False
        return self

    def hide(self) -> Layer:
        """Make this layer invisible."""
        self.visible = False
        return self

    def show_layer(self) -> Layer:
        """Make this layer visible."""
        self.visible = True
        return self

    @classmethod
    def background(cls, **kwargs: Any) -> Layer:
        """Create a background layer (z_index=0, locked by default)."""
        return cls(name="background", z_index=0, locked=True, **kwargs)

    @classmethod
    def foreground(cls, **kwargs: Any) -> Layer:
        """Create an unlocked foreground layer."""
        return cls(name="foreground", z_index=100, **kwargs)

    def render(self, compact: bool = False) -> str:
        sep = "" if compact else "\n"
        inner = sep.join(c.render(compact) for c in self)
        return f"<g id='{self.name}' z-index='{self.z_index}'>{inner}</g>"


class Scene(Container):
    """Root of the scene graph.  Holds ordered :class:`Layer` objects.

    The scene owns the canvas dimensions and provides async rendering.
    """

    def __init__(
        self,
        width:  types.Length = 800,
        height: types.Length = 600,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.width  = width
        self.height = height

    @property
    def size(self) -> tuple[types.Length, types.Length]:
        return (self.width, self.height)

    @property
    def aspect_ratio(self) -> float:
        return float(self.width) / float(self.height)  # type: ignore[arg-type]

    async def render_all_async(self, compact: bool = False) -> str:
        """Render the entire scene asynchronously."""
        parts: list[str] = []
        async for child in self.iter_async():
            parts.append(child.render(compact=compact))
        sep = "" if compact else "\n"
        return (
            f"<svg width='{self.width}' height='{self.height}'>"
            f"{sep.join(parts)}</svg>"
        )

    def render(self, compact: bool = False) -> str:
        sep = "" if compact else "\n"
        inner = sep.join(c.render(compact) for c in self)
        return f"<svg width='{self.width}' height='{self.height}'>{inner}</svg>"

    @classmethod
    def blank(cls, width: types.Length = 800, height: types.Length = 600, **kwargs: Any) -> Scene:
        """Create an empty scene with no layers."""
        return cls(width=width, height=height, **kwargs)
