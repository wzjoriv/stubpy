# demo/export.py  —  PixelForge / export and format conversion
# ------------------------------------------------------------------
# Exercises: TYPE_CHECKING guard, forward references, cross-file imports,
#            module-level constants, Optional params, Union annotations,
#            async functions, *args type spreading.
"""
Export and format-conversion utilities for PixelForge.

Exercises cross-file imports (from element, container, types) including
``TYPE_CHECKING``-guarded annotations so the stubs correctly re-emit the
needed import headers without causing circular imports at runtime.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Sequence

from demo import types
from demo.element import Element

if TYPE_CHECKING:
    # These imports are only needed for type-checking / stub generation.
    # At runtime they would create a circular dependency.
    from demo.container import Container, Scene
    from demo.primitives import RenderOptions, BoundingBox

__all__ = [
    "DEFAULT_DPI",
    "SUPPORTED_FORMATS",
    "export_svg",
    "export_png",
    "export_batch",
    "measure_scene",
    "compute_union_bbox",
]

# ── Module-level constants ────────────────────────────────────────────────

DEFAULT_DPI: float = 96.0
SUPPORTED_FORMATS: frozenset[str] = frozenset({"svg", "png", "pdf", "webp"})


# ── Synchronous export functions ──────────────────────────────────────────

def export_svg(
    scene: Scene,
    path:  str,
    *,
    compact: bool = False,
    indent:  str  = "  ",
) -> int:
    """Render *scene* to an SVG file and return the byte count written.

    Parameters
    ----------
    scene:
        The root scene to export.
    path:
        File-system path for the output ``.svg`` file.
    compact:
        When ``True``, omit decorative whitespace for smaller files.
    indent:
        Indentation string used in non-compact output.

    Returns
    -------
    int
        Number of bytes written.
    """
    svg = scene.render(compact=compact)
    data = svg.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


async def export_png(
    scene:    "Scene",
    path:     str,
    *,
    dpi:      float = DEFAULT_DPI,
    quality:  int   = 90,
    options:  "RenderOptions | None" = None,
) -> int:
    """Async: rasterise *scene* to a PNG file.

    Exercises: async def, TYPE_CHECKING-guarded annotation, Optional union.

    Returns the file size in bytes.
    """
    raise NotImplementedError("PNG export requires the pixelforge-raster plugin")


def export_batch(
    scenes:     Sequence[Scene],
    output_dir: str,
    *,
    fmt:        str = "svg",
    prefix:     str = "scene_",
) -> list[str]:
    """Export every scene in *scenes* to *output_dir*.

    Returns
    -------
    list[str]
        Absolute paths of every file written.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {fmt!r}. Choose from {SUPPORTED_FORMATS}")
    paths: list[str] = []
    for i, scene in enumerate(scenes):
        name = f"{prefix}{i:04d}.{fmt}"
        dest = os.path.join(output_dir, name)
        export_svg(scene, dest)
        paths.append(os.path.abspath(dest))
    return paths


# ── Geometry helpers using cross-file types ───────────────────────────────

def measure_scene(scene: "Scene") -> "BoundingBox":
    """Return the union bounding box of all elements in *scene*."""
    from demo.primitives import BoundingBox as _BB
    boxes = [
        e.bounding_box() for e in scene
        if hasattr(e, "bounding_box")
    ]
    if not boxes:
        return _BB(0.0, 0.0, 0.0, 0.0)
    result = boxes[0]
    for b in boxes[1:]:
        result = result.union(b)
    return result


def compute_union_bbox(*elements: Element) -> types.BoundingBox:
    """Compute the union bounding box of one or more :class:`~demo.element.Element` objects.

    Exercises: ``*args`` with an explicit type annotation preserved in the stub.
    """
    if not elements:
        return (0.0, 0.0, 0.0, 0.0)
    boxes = [e.bounding_box() for e in elements if hasattr(e, "bounding_box")]
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    x  = min(b[0] for b in boxes)
    y  = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x, y, x2 - x, y2 - y)
