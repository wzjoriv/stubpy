# demo/primitives.py  —  PixelForge / special class forms
# -----------------------------------------------------
# Exercises: @dataclass (plain, ClassVar, field defaults), NamedTuple,
#            TypedDict (total, partial), Enum / IntEnum,
#            abstract base class + @abstractmethod, **kwargs MRO backtracing
#            through an ABC hierarchy.
"""
Special class forms used throughout PixelForge.

Covers the full range of Python's typed class patterns:

- :class:`BoundingBox` — NamedTuple for geometry
- :class:`StrokeStyle` — dataclass for render options
- :class:`RenderOptions` — TypedDict for open-ended option dicts
- :class:`BlendMode` — Enum for named constants
- :class:`Shape` — ABC with @abstractmethod + MRO **kwargs backtracing
- :class:`Circle`, :class:`Rect`, :class:`Text` — concrete shapes
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, NamedTuple, TypedDict

from demo import types

__all__ = [
    "BoundingBox",
    "StrokeStyle",
    "RenderOptions",
    "BlendMode",
    "Shape",
    "Circle",
    "Rect",
    "Text",
]


# ── NamedTuple ────────────────────────────────────────────────────────────

class BoundingBox(NamedTuple):
    """Immutable axis-aligned bounding box in scene coordinates."""

    x:      float           # left edge
    y:      float           # top edge
    width:  float           # horizontal extent
    height: float           # vertical extent

    @property
    def right(self) -> float:
        """Right edge (x + width)."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """Bottom edge (y + height)."""
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        """Centre point."""
        return (self.x + self.width / 2, self.y + self.height / 2)

    def union(self, other: "BoundingBox") -> "BoundingBox":
        """Return the smallest box that contains both *self* and *other*."""
        x  = min(self.x, other.x)
        y  = min(self.y, other.y)
        x2 = max(self.right, other.right)
        y2 = max(self.bottom, other.bottom)
        return BoundingBox(x, y, x2 - x, y2 - y)


# ── dataclass ─────────────────────────────────────────────────────────────

@dataclass
class StrokeStyle:
    """Stroke (outline) parameters for a drawn shape.

    ``width`` is in scene units; ``dash_pattern`` is a list of on/off
    lengths for dashed lines (empty list means solid).
    """

    color:        types.Color   = field(default=(0.0, 0.0, 0.0, 1.0))
    width:        float         = 1.0
    line_cap:     str           = "butt"   # "butt" | "round" | "square"
    line_join:    str           = "miter"  # "miter" | "round" | "bevel"
    dash_pattern: list[float]   = field(default_factory=list)

    _DEFAULT_SOLID: ClassVar["StrokeStyle"]   # populated at module level below


# Populate the ClassVar sentinel after the class is defined
StrokeStyle._DEFAULT_SOLID = StrokeStyle()


# ── TypedDict (total=False — all keys optional) ───────────────────────────

class RenderOptions(TypedDict, total=False):
    """Open-ended dict of per-render knobs.

    All keys are optional; pass only those you want to override.
    """

    compact:  bool    # omit insignificant whitespace
    indent:   str     # indentation string for non-compact output
    encoding: str     # output byte encoding
    dpi:      float   # dots per inch for unit conversion
    antialias: bool   # enable sub-pixel antialiasing


# ── Enum ──────────────────────────────────────────────────────────────────

class BlendMode(enum.Enum):
    """Compositing blend mode, matching CSS mix-blend-mode values."""

    NORMAL      = "normal"
    MULTIPLY    = "multiply"
    SCREEN      = "screen"
    OVERLAY     = "overlay"
    DARKEN      = "darken"
    LIGHTEN     = "lighten"
    COLOR_DODGE = "color-dodge"
    COLOR_BURN  = "color-burn"
    HARD_LIGHT  = "hard-light"
    SOFT_LIGHT  = "soft-light"
    DIFFERENCE  = "difference"
    EXCLUSION   = "exclusion"


class LineCap(enum.Enum):
    """SVG stroke-linecap values."""

    BUTT   = "butt"
    ROUND  = "round"
    SQUARE = "square"


# ── Abstract base class + **kwargs MRO backtracing ────────────────────────

class Shape(ABC):
    """Abstract base for all PixelForge drawable primitives.

    Concrete subclasses must implement :meth:`area`, :meth:`bounding_box`,
    and :meth:`render`.  The ``__init__`` accepts common visual style
    options as ``**kwargs`` so subclasses can forward them without
    listing every parameter.
    """

    #: Count of all Shape instances created in this process.
    _instance_count: ClassVar[int] = 0

    def __init__(
        self,
        *,
        fill:       types.Color | None = None,
        stroke:     StrokeStyle | None = None,
        opacity:    float               = 1.0,
        blend_mode: BlendMode           = BlendMode.NORMAL,
        visible:    bool                = True,
    ) -> None:
        Shape._instance_count += 1
        self.fill       = fill
        self.stroke     = stroke
        self.opacity    = opacity
        self.blend_mode = blend_mode
        self.visible    = visible

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    def area(self) -> float:
        """Return the enclosed area in scene units²."""
        ...

    @abstractmethod
    def bounding_box(self) -> BoundingBox:
        """Return the tight axis-aligned bounding box."""
        ...

    @abstractmethod
    def render(self, *, compact: bool = False) -> str:
        """Render to an SVG fragment string."""
        ...

    # ── Concrete helpers ──────────────────────────────────────────────

    @classmethod
    def count(cls) -> int:
        """Return the total number of Shape instances created."""
        return cls._instance_count

    def describe(self) -> str:
        """Human-readable one-liner summary."""
        return (
            f"{type(self).__name__}("
            f"opacity={self.opacity}, blend={self.blend_mode.value!r})"
        )

    def is_visible(self) -> bool:
        """Return ``True`` when the shape should be drawn."""
        return self.visible and self.opacity > 0.0


class Circle(Shape):
    """A filled circle or ring (if stroke-only)."""

    def __init__(self, cx: float, cy: float, radius: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cx     = cx
        self.cy     = cy
        self.radius = radius

    def area(self) -> float:
        import math
        return math.pi * self.radius ** 2

    def bounding_box(self) -> BoundingBox:
        r = self.radius
        return BoundingBox(self.cx - r, self.cy - r, 2 * r, 2 * r)

    def render(self, *, compact: bool = False) -> str:
        sep = "" if compact else " "
        return (
            f'<circle{sep}cx="{self.cx}"{sep}cy="{self.cy}"'
            f'{sep}r="{self.radius}"/>'
        )

    @classmethod
    def unit(cls, **kwargs) -> "Circle":
        """Create a unit circle centred at the origin."""
        return cls(0.0, 0.0, 1.0, **kwargs)


class Rect(Shape):
    """An axis-aligned rectangle."""

    def __init__(
        self,
        x:      float,
        y:      float,
        width:  float,
        height: float,
        *,
        rx: float = 0.0,
        ry: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.x      = x
        self.y      = y
        self.width  = width
        self.height = height
        self.rx     = rx    # corner radius X
        self.ry     = ry    # corner radius Y

    def area(self) -> float:
        return self.width * self.height

    def bounding_box(self) -> BoundingBox:
        return BoundingBox(self.x, self.y, self.width, self.height)

    def render(self, *, compact: bool = False) -> str:
        sep = "" if compact else " "
        parts = [
            f'<rect{sep}x="{self.x}"{sep}y="{self.y}"',
            f'{sep}width="{self.width}"{sep}height="{self.height}"',
        ]
        if self.rx:
            parts.append(f'{sep}rx="{self.rx}"')
        if self.ry:
            parts.append(f'{sep}ry="{self.ry}"')
        parts.append("/>")
        return "".join(parts)


class Text(Shape):
    """A text element positioned at (*x*, *y*)."""

    def __init__(
        self,
        content:   str,
        x:         float,
        y:         float,
        *,
        font_size:  float = 16.0,
        font_family: str  = "sans-serif",
        anchor:    str    = "start",   # "start" | "middle" | "end"
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.content     = content
        self.x           = x
        self.y           = y
        self.font_size   = font_size
        self.font_family = font_family
        self.anchor      = anchor

    def area(self) -> float:
        # Approximate: character-count × em²
        return len(self.content) * self.font_size ** 2 * 0.6

    def bounding_box(self) -> BoundingBox:
        estimated_width = len(self.content) * self.font_size * 0.6
        return BoundingBox(self.x, self.y - self.font_size, estimated_width, self.font_size)

    def render(self, *, compact: bool = False) -> str:
        sep = "" if compact else " "
        return (
            f'<text{sep}x="{self.x}"{sep}y="{self.y}"'
            f'{sep}font-size="{self.font_size}"'
            f'{sep}text-anchor="{self.anchor}">'
            f"{self.content}</text>"
        )
