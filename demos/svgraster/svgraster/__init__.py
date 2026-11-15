"""svgraster: render SVG 1.1 documents into numpy RGBA arrays.

Usage::

    import svgraster

    image = svgraster.render('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                             '<circle cx="32" cy="32" r="24" fill="teal"/></svg>')
    image.shape          # (64, 64, 4), dtype uint8
    svgraster.Renderer(antialias=4, supersample=2).render("drawing.svg", dtype="float32")
    svgraster.backend_info()["scanline"]["available"]

Every native layer is optional; without it the numpy fallback is used.

Sub-packages:

- ``svgraster.dom``: XML loading, CSS cascade, colors, units and transforms.
- ``svgraster.parse``: path data, basic shapes, flattening and viewports.
- ``svgraster.raster``: coverage (C API), stroking and compositing (nanobind),
  gradients and patterns (Cython).
- ``svgraster.filters``: filter primitives (pybind11).
- ``svgraster.render``: the renderer, paint servers, clipping, masking,
  markers, filters and text.
- ``svgraster.io``: PNG, PPM and ``.npy`` output.
"""
from ._backend import backend_info, pure_python
from .dom import Color, Document, Matrix, parse_color
from .io import read_png, save, write_png
from .raster import GradientLUT, Rasterizer
from .render import Renderer, render, render_file

__version__ = "0.1.0"
__author__ = "Josue N Rivera"

__all__ = [
    "Color",
    "Document",
    "GradientLUT",
    "Matrix",
    "Rasterizer",
    "Renderer",
    "backend_info",
    "parse_color",
    "pure_python",
    "read_png",
    "render",
    "render_file",
    "save",
    "write_png",
]
