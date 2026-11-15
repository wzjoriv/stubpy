"""Rasterizing documents with skia's SVG renderer."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from ..attributes.length import Length
from ._skia import require_skia

if TYPE_CHECKING:
    from ..document import Document

__all__ = ["DEFAULT_SIZE", "rasterize", "skia_renderer"]

DEFAULT_SIZE: Final = 300.0


def _size(document: Document) -> tuple[int, int]:
    root = document.root
    box = root.view_box
    width, height = root.get("width"), root.get("height")
    w = Length.parse(width).to_user_units() if width is not None else (box.width if box else DEFAULT_SIZE)
    h = Length.parse(height).to_user_units() if height is not None else (box.height if box else DEFAULT_SIZE)
    return max(1, math.ceil(w)), max(1, math.ceil(h))


def rasterize(document: Document, *, scale: float = 1.0, background: str | None = None) -> bytes:
    """Render *document* to PNG bytes with skia.

    Parameters
    ----------
    document : Document
        What to draw. SMIL animation elements are not evaluated.
    scale : float
        Output pixels per user unit.
    background : str, optional
        A color painted under the drawing; transparent when omitted.
    """
    skia = require_skia("rasterizing")
    from ..color.color import parse_color

    width, height = _size(document)
    stream = skia.MemoryStream(document.to_string().encode("utf-8"))
    dom = skia.SVGDOM.MakeFromStream(stream)
    surface = skia.Surface(max(1, round(width * scale)), max(1, round(height * scale)))
    with surface as canvas:
        if background is not None:
            color = parse_color(background)
            canvas.clear(skia.Color(color.r, color.g, color.b))
        canvas.scale(scale, scale)
        dom.setContainerSize(skia.Size(width, height))
        dom.render(canvas)
    return bytes(surface.makeImageSnapshot().encodeToData())


def skia_renderer(document: Document, time: float) -> bytes:
    """Frame renderer for :func:`~svgwriter.animate.render_animation`.

    Draws the document as it is at each frame; use ``update=`` to change
    it over time.
    """
    del time
    return rasterize(document, background="white")
