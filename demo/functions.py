# demo/functions.py
# Module-level utility functions for the drawing library.
# Exercises: sync functions, async functions, __all__ filtering,
#            private functions, kw-only params, *args, **kwargs.
from __future__ import annotations

from typing import Iterator, Optional, Sequence

from demo import types
from demo.element import Element

__all__ = [
    "make_color",
    "lerp_color",
    "clamp",
    "parse_length",
    "walk_elements",
    "render_to_string",
    "render_to_file",
]

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def make_color(r: float, g: float, b: float, a: float = 1.0) -> types.Color:
    """Build a normalised RGBA colour tuple (values 0–1)."""
    return (
        max(0.0, min(1.0, r)),
        max(0.0, min(1.0, g)),
        max(0.0, min(1.0, b)),
        max(0.0, min(1.0, a)),
    )


def lerp_color(a: types.Color, b: types.Color, t: float) -> types.Color:
    """Linearly interpolate between two colours.

    Only supports tuple-form colours. String colours raise ``TypeError``.
    """
    if not isinstance(a, tuple) or not isinstance(b, tuple):
        raise TypeError("lerp_color requires tuple-form colours")
    result = tuple(
        av + (bv - av) * t
        for av, bv in zip(a, b)
    )
    return result  # type: ignore[return-value]


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
