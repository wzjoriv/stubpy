# demo/element.py
# Abstract base element — every drawable object inherits from this.
# Exercises: @abstractmethod, @property, @classmethod with **kwargs,
#            async method, NamedTuple, __all__, private variables.
from __future__ import annotations

import abc
from typing import Any, Dict, Iterator, NamedTuple, Optional
from demo import types

__all__ = ["Style", "Transform", "Element"]

# ---------------------------------------------------------------------------
# Public value types
# ---------------------------------------------------------------------------

class Transform(NamedTuple):
    """Immutable affine-transform snapshot attached to an element."""
    translate_x: float = 0.0
    translate_y: float = 0.0
    rotate_deg:  float = 0.0
    scale_x:     float = 1.0
    scale_y:     float = 1.0


# ---------------------------------------------------------------------------
# Style bag
# ---------------------------------------------------------------------------

class Style:
    """Key/value CSS-style property bag.

    Supports dict-like access and iteration.  Changes are not validated —
    callers are responsible for supplying valid CSS property names and values.
    """

    # Internal default properties applied when no explicit value is set.
    _DEFAULTS: dict[str, Any] = {
        "opacity": 1.0,
        "visibility": "visible",
    }

    def __init__(self, **props: Any) -> None:
        self._data: Dict[str, Any] = {**self._DEFAULTS, **props}

    # -- Mapping interface ---------------------------------------------------

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    # -- Factories -----------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Style:
        """Create a :class:`Style` from an existing mapping."""
        return cls(**data)

    @classmethod
    def merge(cls, base: Style, override: Style) -> Style:
        """Return a new :class:`Style` with *override* values winning."""
        merged = dict(base._data)
        merged.update(override._data)
        return cls(**merged)

    # -- Rendering -----------------------------------------------------------

    def render(self) -> str:
        """Return a CSS inline-style string."""
        return "; ".join(f"{k}: {v}" for k, v in self._data.items())


# ---------------------------------------------------------------------------
# Abstract base element
# ---------------------------------------------------------------------------

class Element(abc.ABC):
    """Abstract base for every drawable object in the scene graph.

    Subclasses must implement :meth:`render` and :meth:`bounding_box`.
    Everything else (transform, style, id, visibility) is handled here.
    """

    def __init__(
        self,
        id:      Optional[str]   = None,
        title:   Optional[str]   = None,
        opacity: float            = 1.0,
        visible: bool             = True,
    ) -> None:
        self.id       = id
        self.title    = title
        self.opacity  = opacity
        self.visible  = visible
        self.style    = Style()
        self._transform = Transform()

    # -- Abstract interface --------------------------------------------------

    @abc.abstractmethod
    def render(self, compact: bool = False) -> str:
        """Serialise this element to an SVG/markup string."""

    @property
    @abc.abstractmethod
    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return the axis-aligned bounding box ``(x, y, width, height)``."""

    # -- Async rendering -----------------------------------------------------

    async def render_async(self, compact: bool = False) -> str:
        """Async variant of :meth:`render` for non-blocking pipelines."""
        return self.render(compact=compact)

    # -- Transform helpers (chainable) ---------------------------------------

    def translate(self, tx: float, ty: float = 0.0) -> Element:
        t = self._transform
        self._transform = Transform(
            t.translate_x + tx, t.translate_y + ty,
            t.rotate_deg, t.scale_x, t.scale_y,
        )
        return self

    def rotate(
        self,
        angle:  float,
        cx:     Optional[float] = None,
        cy:     Optional[float] = None,
    ) -> Element:
        t = self._transform
        self._transform = Transform(
            t.translate_x, t.translate_y,
            t.rotate_deg + angle,
            t.scale_x, t.scale_y,
        )
        return self

    def scale(self, sx: float, sy: Optional[float] = None) -> Element:
        t = self._transform
        self._transform = Transform(
            t.translate_x, t.translate_y, t.rotate_deg,
            t.scale_x * sx, t.scale_y * (sy if sy is not None else sx),
        )
        return self

    def reset_transform(self) -> Element:
        self._transform = Transform()
        return self

    # -- Style helpers -------------------------------------------------------

    def apply(self, **props: Any) -> Element:
        """Set one or more CSS style properties and return self."""
        for k, v in props.items():
            self.style[k] = v
        return self

    # -- Properties ----------------------------------------------------------

    @property
    def transform(self) -> Transform:
        """Current accumulated transform snapshot (read-only snapshot)."""
        return self._transform

    @property
    def is_visible(self) -> bool:
        """``True`` when the element is both visible and fully opaque enough to see."""
        return self.visible and self.opacity > 0.0

    # -- Factories -----------------------------------------------------------

    @classmethod
    def blank(cls, **kwargs: Any) -> Element:
        """Create a fully transparent (opacity=0) element with all defaults."""
        return cls(opacity=0.0, **kwargs)

    # -- Dunder --------------------------------------------------------------

    def __repr__(self) -> str:
        return self.render()
