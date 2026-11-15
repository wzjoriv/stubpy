"""svgraster: render SVG 1.1 documents (with text, images, filters and SMIL animation) into numpy arrays.

Usage::

    import svgraster

    image = svgraster.render('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                             '<circle cx="32" cy="32" r="24" fill="teal"/></svg>')
    image.shape                                   # (64, 64, 4), dtype uint8
    frame = svgraster.render("spinner.svg", time=0.5, background="white")
    svgraster.render_animation("spinner.svg", "spinner.mp4", fps=30)
    svgraster.Renderer(antialias=8, supersample=2).render("drawing.svg", dtype="float32")
    svgraster.backend_info()["scanline"]["openmp"]

Every native layer is optional; without it the numpy fallback is used.

Sub-packages:

- ``svgraster.dom``: XML loading, CSS cascade and selectors, colors, units and transforms.
- ``svgraster.parse``: path data, basic shapes, flattening and viewports.
- ``svgraster.raster``: coverage (C API), stroking and compositing (nanobind),
  gradients, patterns and resampling (Cython).
- ``svgraster.filters``: filter primitives (pybind11).
- ``svgraster.fonts``: TrueType/OpenType and SVG font parsing, discovery and matching.
- ``svgraster.render``: the renderer, paint servers, clipping, masking, markers,
  filters, images and text layout.
- ``svgraster.animation``: SMIL timing and interpolation, snapshots, frames and video.
- ``svgraster.io``: PNG and JPEG decoding, PNG/PPM/``.npy`` output and resource loading.
"""
from ._backend import backend_info, pure_python
from .animation import FFmpegNotFoundError, frame_renderer, frames, render_animation, snapshot, timeline
from .dom import Color, Document, Matrix, parse_color
from .fonts import Font, FontDatabase, add_font_path
from .io import read_png, save, write_png
from .raster import GradientLUT, Rasterizer
from .render import Renderer, render, render_file, render_frame

__version__ = "0.2.0"
__author__ = "Josue N Rivera"

__all__ = [
    "Color",
    "Document",
    "FFmpegNotFoundError",
    "Font",
    "FontDatabase",
    "GradientLUT",
    "Matrix",
    "Rasterizer",
    "Renderer",
    "add_font_path",
    "backend_info",
    "frame_renderer",
    "frames",
    "parse_color",
    "pure_python",
    "read_png",
    "render",
    "render_animation",
    "render_file",
    "render_frame",
    "save",
    "snapshot",
    "timeline",
    "write_png",
]
