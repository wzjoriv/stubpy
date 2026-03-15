# demo/container.py
# Tests cross-file import: Container extends Element (from element.py),
# holds a list of Element children, and uses *elements + **kwargs.
from __future__ import annotations

from typing import Iterator, List, Optional
from demo.element import Element


class Container(Element):
    """
    Holds an ordered list of child Elements.
    *elements are the initial children; **kwargs flow up to Element.__init__.

    This is the primary cross-file test case:
      - Element is defined in element.py
      - Container imports it and uses it as a param type + base class
      - The .pyi should show Element (not inline its definition)
      - *elements: Element must survive because it is explicitly annotated
      - **kwargs must resolve to id, title, opacity from Element.__init__
    """

    def __init__(
        self,
        *elements: Element,
        label: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.elements: List[Element] = list(elements)
        self.label = label

    # ── child management ────────────────────────────────────────────────────

    def add(self, *elements: Element) -> Container:
        """Append one or more children; returns self for chaining."""
        self.elements.extend(elements)
        return self

    def remove(self, element: Element) -> Container:
        self.elements.remove(element)
        return self

    def get(self, index: int) -> Element:
        return self.elements[index]

    def __iter__(self) -> Iterator[Element]:
        return iter(self.elements)

    def __len__(self) -> int:
        return len(self.elements)

    # ── cloning ─────────────────────────────────────────────────────────────

    def clone(self, deep: bool = True) -> Container:
        """Return a shallow or deep copy of this container."""
        import copy
        return copy.deepcopy(self) if deep else copy.copy(self)

    # ── rendering ───────────────────────────────────────────────────────────

    def render(self, compact: bool = False) -> str:
        children = "\n".join(c.render(compact=compact) for c in self.elements)
        return f"<g>{children}</g>"


class Layer(Container):
    """
    A named, optionally locked rendering layer.
    Tests three-level cross-file chain:
      Layer(**kwargs) → Container(**kwargs) → Element(**kwargs)
    """

    def __init__(
        self,
        name: str,
        locked: bool = False,
        visible: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.name    = name
        self.locked  = locked
        self.visible = visible

    def lock(self) -> Layer:
        self.locked = True
        return self

    def unlock(self) -> Layer:
        self.locked = False
        return self

    def hide(self) -> Layer:
        self.visible = False
        return self

    def show_layer(self) -> Layer:
        self.visible = True
        return self