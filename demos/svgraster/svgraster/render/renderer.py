"""The :class:`Renderer` that turns SVG sources into numpy images."""
from __future__ import annotations

import os

import numpy as np

from .. import _backend, _jit
from ..dom.color import Color, parse_color
from ..dom.document import Document
from ..dom.transform import Matrix
from ..dom.units import CSS_DPI, parse_fraction, parse_length
from ..parse.viewport import parse_aspect_ratio, parse_viewbox, viewbox_transform
from ..raster import composite
from ..raster.scanline import DEFAULT_SAMPLES, MAX_SAMPLES
from ._draw import Drawer

DEFAULT_SIZE = 100.0
DTYPES = ("uint8", "float32")
MAX_SUPERSAMPLE = 8
MAX_PIXELS = 1 << 28
THREADED_LAYERS = ("scanline", "paint", "pattern", "filters", "composite")
BYTE_MAX = 255.0


def _background(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        color = parse_color(value)
        if color is None:
            raise ValueError(f"invalid background color {value!r}")
    else:
        channels = [float(v) for v in value]
        if len(channels) not in (3, 4):
            raise ValueError("background must be a color string or 3 or 4 channel values")
        if any(v > 1.0 for v in channels):
            channels = [v / BYTE_MAX for v in channels]
        color = Color(*channels)
    return color.premultiplied()


def intrinsic_size(doc: Document) -> tuple[float, float]:
    """The document's width and height in CSS pixels."""
    root = doc.root
    box = parse_viewbox(root.get("viewBox"))
    units = root.units((0.0, 0.0))

    def dim(name: str, axis: str, vb_dim: float | None) -> float | None:
        raw = root.get(name)
        if raw is None or raw.strip() == "auto":
            return None
        if raw.strip().endswith("%"):
            return (vb_dim if vb_dim is not None else DEFAULT_SIZE) * parse_fraction(raw, 1.0)
        value = parse_length(raw, units, axis, -1.0)
        return value if value >= 0 else None

    w = dim("width", "x", box.width if box else None)
    h = dim("height", "y", box.height if box else None)
    if box is not None:
        if w is None and h is None:
            w, h = box.width, box.height
        elif w is None:
            w = h * box.width / box.height
        elif h is None:
            h = w * box.height / box.width
    return (DEFAULT_SIZE if w is None else w, DEFAULT_SIZE if h is None else h)


class Renderer:
    """Configurable SVG rasterizer.

    ``antialias`` is the number of sub-scanlines per pixel row, ``supersample``
    renders at an integer multiple and box-filters down, ``threads`` caps
    OpenMP threads in the native layers, ``native=False`` forces numpy and
    ``fonts`` is a :class:`~svgraster.fonts.FontDatabase` to use instead of the
    system fonts.
    """

    def __init__(self, *, antialias: int = DEFAULT_SAMPLES, supersample: int = 1, threads: int | None = None,
                 tolerance: float = 0.1, native: bool = True, fonts=None):
        if not 1 <= antialias <= MAX_SAMPLES:
            raise ValueError(f"antialias must be in 1..{MAX_SAMPLES}")
        if not 1 <= supersample <= MAX_SUPERSAMPLE:
            raise ValueError(f"supersample must be in 1..{MAX_SUPERSAMPLE}")
        if tolerance <= 0:
            raise ValueError("tolerance must be positive")
        if threads is not None and threads < 1:
            raise ValueError("threads must be at least 1")
        self.antialias = antialias
        self.supersample = supersample
        self.threads = threads
        self.tolerance = tolerance
        self.native = native
        self.fonts = fonts

    def __repr__(self) -> str:
        return (f"Renderer(antialias={self.antialias}, supersample={self.supersample}, "
                f"threads={self.threads}, tolerance={self.tolerance}, native={self.native})")

    def _apply_threads(self) -> None:
        if self.threads is None:
            return
        for layer in THREADED_LAYERS:
            mod = _backend.module(layer)
            if mod is not None and hasattr(mod, "set_num_threads"):
                mod.set_num_threads(int(self.threads))

    def render(self, svg, *, width: int | None = None, height: int | None = None, dpi: float = CSS_DPI,
               background=None, dtype: str = "uint8", premultiplied: bool = False, time: float | None = None,
               base_dir: str | os.PathLike | None = None) -> np.ndarray:
        """Render markup, a path, bytes or an object with ``__svg__()``/``to_string()`` to ``(H, W, 4)`` RGBA.

        ``time`` (seconds) evaluates SMIL animations; ``base_dir`` resolves relative references.
        """
        return self.render_document(Document.parse(svg, base_dir=base_dir), width=width, height=height, dpi=dpi,
                                    background=background, dtype=dtype, premultiplied=premultiplied, time=time)

    def render_document(self, doc: Document, *, width: int | None = None, height: int | None = None,
                        dpi: float = CSS_DPI, background=None, dtype: str = "uint8",
                        premultiplied: bool = False, time: float | None = None) -> np.ndarray:
        """Render an already parsed :class:`~svgraster.dom.Document`."""
        if dtype not in DTYPES:
            raise ValueError(f"dtype must be one of {DTYPES}, not {dtype!r}")
        if dpi <= 0:
            raise ValueError("dpi must be positive")
        if time is not None:
            from ..animation import snapshot

            doc = snapshot(doc, float(time))
        with _backend.pure_python(not self.native):
            self._apply_threads()
            canvas = self._render_premultiplied(doc, width, height, dpi)
            bg = _background(background)
            if bg is not None:
                canvas = canvas + np.asarray(bg, dtype=np.float32) * (1.0 - canvas[..., 3:4])
            if dtype == "uint8":
                return composite.to_uint8(canvas, unpremultiply=not premultiplied)
            if premultiplied:
                return np.clip(canvas, 0.0, 1.0)
            return np.clip(_jit.unpremultiply(canvas, use_jit=self.native), 0.0, 1.0)

    def output_size(self, doc: Document, width: int | None = None, height: int | None = None,
                    dpi: float = CSS_DPI) -> tuple[int, int]:
        """``(width, height)`` in pixels for a render of ``doc``."""
        w, h = intrinsic_size(doc)
        scale = dpi / CSS_DPI
        if width is not None and height is None and w > 0:
            height = max(1, round(width * h / w))
        elif height is not None and width is None and h > 0:
            width = max(1, round(height * w / h))
        out_w = int(width) if width is not None else max(1, round(w * scale))
        out_h = int(height) if height is not None else max(1, round(h * scale))
        if out_w <= 0 or out_h <= 0:
            raise ValueError("output size must be positive")
        if out_w * out_h * self.supersample ** 2 > MAX_PIXELS:
            raise ValueError(f"output size {out_w}x{out_h} (supersample {self.supersample}) is too large")
        return out_w, out_h

    def _render_premultiplied(self, doc: Document, width, height, dpi) -> np.ndarray:
        w, h = intrinsic_size(doc)
        out_w, out_h = self.output_size(doc, width, height, dpi)
        ss = self.supersample
        canvas = np.zeros((out_h * ss, out_w * ss, 4), dtype=np.float32)
        if w <= 0 or h <= 0:
            return np.zeros((out_h, out_w, 4), dtype=np.float32)
        root = doc.root
        box = parse_viewbox(root.get("viewBox"))
        ctm = Matrix.scale(out_w * ss / w, out_h * ss / h)
        viewport = (w, h)
        aspect = parse_aspect_ratio(root.get("preserveAspectRatio"))
        if box is not None and width is not None and height is not None:
            ctm = Matrix.scale(ss) @ viewbox_transform(box, out_w, out_h, aspect)
            viewport = (box.width, box.height)
        elif box is not None:
            ctm = ctm @ viewbox_transform(box, w, h, aspect)
            viewport = (box.width, box.height)
        drawer = Drawer(doc, samples=self.antialias, tolerance=self.tolerance, fonts=self.fonts, renderer=self)
        drawer.draw(root, canvas, ctm, viewport)
        return _jit.downscale(canvas, ss, use_jit=self.native) if ss > 1 else canvas


RENDERER_OPTIONS = ("antialias", "supersample", "threads", "tolerance", "native", "fonts")


def render(svg, *, width: int | None = None, height: int | None = None, dpi: float = CSS_DPI, background=None,
           dtype: str = "uint8", time: float | None = None, **options) -> np.ndarray:
    """Render SVG (markup, path, bytes or an object with ``__svg__()``/``to_string()``) to RGBA.

    ``time`` evaluates SMIL animations at that many seconds. ``**options`` configure the
    :class:`Renderer` (``antialias``, ``supersample``, ``threads``, ``tolerance``, ``native``,
    ``fonts``); ``premultiplied`` and ``base_dir`` are passed to :meth:`Renderer.render`.
    """
    extra = {k: options.pop(k) for k in ("premultiplied", "base_dir") if k in options}
    unknown = set(options) - set(RENDERER_OPTIONS)
    if unknown:
        raise TypeError(f"render() got unexpected keyword arguments: {', '.join(sorted(unknown))}")
    return Renderer(**options).render(svg, width=width, height=height, dpi=dpi, background=background,
                                      dtype=dtype, time=time, **extra)


def render_frame(document, seconds: float, **kwargs) -> np.ndarray:
    """``(document, seconds) -> RGBA uint8``: the shape animation hooks expect (``"svgraster:render_frame"``)."""
    return render(document, time=seconds, **kwargs)


def render_file(path: str | os.PathLike, output: str | os.PathLike | None = None, **kwargs) -> np.ndarray:
    """Render the SVG file at ``path``, optionally saving to ``output`` (.png/.ppm/.npy)."""
    from ..io import save

    image = render(os.fspath(path) if not isinstance(path, bytes) else path, **kwargs)
    if output is not None:
        save(image, output)
    return image
