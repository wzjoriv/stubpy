# demo/functions.py
# Module-level utility functions for the drawing library.
# Exercises: sync functions, async functions, __all__ filtering,
#            private functions, kw-only params, *args, **kwargs backtracing,
#            chained forwarding, positional-only params (/), typed *args,
#            mixed defaults/no-defaults after **kwargs expansion.
from __future__ import annotations

from typing import Iterator, Optional, Sequence

from demo import types
from demo.element import Element

__all__ = [
    # colour helpers
    "make_color",
    "lerp_color",
    "make_color_red",
    "make_color_blue",
    "make_color_tinted",
    # numeric utilities
    "clamp",
    "parse_length",
    # pos-only / kw-only demos
    "normalise_range",
    "scaled_clamp",
    # *args forwarding
    "stack_colors",
    "blend_colors",
    # scene traversal
    "walk_elements",
    # rendering helpers
    "render_to_string",
    "render_to_file",
]


# ---------------------------------------------------------------------------
# Core colour builder — target for **kwargs backtracing
# ---------------------------------------------------------------------------

def make_color(r: float, g: float, b: float, a: float = 1.0) -> types.Color:
    """Build a normalised RGBA colour tuple (values 0–1)."""
    return (
        max(0.0, min(1.0, r)),
        max(0.0, min(1.0, g)),
        max(0.0, min(1.0, b)),
        max(0.0, min(1.0, a)),
    )


# ── Simple **kwargs forwarding ────────────────────────────────────────────

def make_color_red(r: float = 1.0, **kwargs) -> types.Color:
    """Red-channel shortcut; remaining channels forwarded to make_color."""
    return make_color(r=r, **kwargs)


def make_color_blue(b: float = 1.0, **kwargs) -> types.Color:
    """Blue-channel shortcut; remaining channels forwarded to make_color."""
    return make_color(b=b, **kwargs)


# ── Chained **kwargs forwarding: make_color_tinted → make_color_red → make_color
#    Tests recursive resolution depth > 1.

def make_color_tinted(tint: float = 0.5, **kwargs) -> types.Color:
    """Apply a tint and forward to the red shortcut."""
    return make_color_red(r=tint, **kwargs)


# ---------------------------------------------------------------------------
# Positional-only params (PEP 570) — the `/` separator
# ---------------------------------------------------------------------------

def normalise_range(value: float, lo: float, hi: float, /) -> float:
    """Map *value* from [lo, hi] to [0, 1].  All params are positional-only."""
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)


def scaled_clamp(value: float, lo: float = 0.0, hi: float = 1.0, /, *, scale: float = 1.0) -> float:
    """Clamp then scale.  Positional-only params before ``/``, kw-only after ``*``."""
    return max(lo, min(hi, value)) * scale


# ---------------------------------------------------------------------------
# Numeric utilities
# ---------------------------------------------------------------------------

def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to the closed interval [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def parse_length(value: types.Length, *, dpi: float = 96.0) -> float:
    """Convert a :data:`~demo.types.Length` to device pixels.

    Handles ``int``, ``float``, and CSS strings ending in ``px``, ``pt``,
    or ``%`` (where ``%`` is relative to 100 device pixels).
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.endswith("px"):
        return float(s[:-2])
    if s.endswith("pt"):
        return float(s[:-2]) * dpi / 72.0
    if s.endswith("%"):
        return float(s[:-1])
    return float(s)


# ---------------------------------------------------------------------------
# *args forwarding — base and wrapper
# ---------------------------------------------------------------------------

def stack_colors(*colors: types.Color, gamma: float = 1.0) -> list[types.Color]:
    """Return *colors* as a list, applying a gamma correction hint."""
    return list(colors)


def blend_colors(*colors: types.Color, **kwargs) -> types.Color:
    """Average *colors* and forward additional options to make_color.

    Exercises: both ``*args`` forwarding (to stack_colors) and ``**kwargs``
    forwarding (to make_color) in the same function.
    """
    stacked = stack_colors(*colors, **kwargs)
    if not stacked:
        return make_color(0.0, 0.0, 0.0)
    n = len(stacked)
    r = sum(c[0] for c in stacked if isinstance(c, tuple)) / n
    g = sum(c[1] for c in stacked if isinstance(c, tuple)) / n
    b = sum(c[2] for c in stacked if isinstance(c, tuple)) / n
    return make_color(r, g, b, **kwargs)


# ---------------------------------------------------------------------------
# Scene traversal
# ---------------------------------------------------------------------------

def walk_elements(root: Element, *, depth_first: bool = True) -> Iterator[Element]:
    """Recursively yield every element in the subtree rooted at *root*.

    Uses depth-first pre-order by default; pass ``depth_first=False`` for
    breadth-first order.
    """
    yield root
    children = getattr(root, "_children", [])
    if depth_first:
        for child in children:
            yield from walk_elements(child, depth_first=True)
    else:
        queue = list(children)
        while queue:
            node = queue.pop(0)
            yield node
            queue.extend(getattr(node, "_children", []))


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def render_to_string(
    root:    Element,
    *,
    compact: bool = False,
    indent:  str  = "  ",
) -> str:
    """Render *root* to an SVG string.

    Parameters
    ----------
    root:
        The root element (usually a :class:`~demo.container.Scene`).
    compact:
        When ``True``, omit all whitespace between elements.
    indent:
        Indentation string used in non-compact output.
    """
    return root.render(compact=compact)


async def render_to_file(
    root:     Element,
    path:     str,
    *,
    compact:  bool          = False,
    encoding: str           = "utf-8",
) -> int:
    """Async: render *root* and write the SVG to *path*.

    Returns the number of bytes written.
    """
    import aiofiles  # type: ignore[import]
    content = root.render(compact=compact)
    encoded = content.encode(encoding)
    async with aiofiles.open(path, "wb") as fh:
        await fh.write(encoded)
    return len(encoded)


# ---------------------------------------------------------------------------
# Private helpers (not in __all__)
# ---------------------------------------------------------------------------

def _resolve_color_string(color: str) -> types.Color:
    """Parse a CSS hex colour string to an RGB tuple."""
    hex_color = color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def _bbox_union(
    *boxes: types.BoundingBox,
) -> types.BoundingBox:
    """Compute the union of one or more bounding boxes."""
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    x  = min(b[0] for b in boxes)
    y  = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x, y, x2 - x, y2 - y)
