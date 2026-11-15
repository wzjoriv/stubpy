# svgraster

Render SVG 1.1 documents into numpy arrays (`H x W x 4` RGBA, `uint8` or
`float32`). The only runtime dependency is numpy. The hot paths are native,
and each native layer uses a different way of writing a compiled Python
extension. Each one has a numpy fallback, so the package works unbuilt and
the tests compare every native layer against its fallback.

```python
import svgraster

img = svgraster.render("drawing.svg")                       # uint8, straight alpha
img = svgraster.render(markup, width=512, background="white", dtype="float32")
r = svgraster.Renderer(antialias=8, supersample=2, threads=4)
img = r.render(b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>")
svgraster.render_file("in.svg", "out.png")
svgraster.backend_info()                                     # which native layers are built
```

```
python -m svgraster drawing.svg -o drawing.png [--width N] [--height N] [--dpi 96]
                    [--background white] [--antialias 16] [--supersample 1]
                    [--threads N] [--float] [--pure] [--backends]
```

Outputs are `.png` (encoded with `zlib`, no imaging library), binary `.ppm`
(alpha composited over white) and `.npy`.

## Building

```
cd demos/svgraster
../../.venv/Scripts/python.exe setup.py build_ext --inplace
```

The build runs single-threaded. Every extension is optional. A missing
toolchain or a failed compile is reported and skipped. OpenMP (`/openmp` on
MSVC) is tried first, and the build retries without it if that fails.
`SVGRASTER_SKIP=capi,cython,pybind11,nanobind` skips layers, and
`SVGRASTER_NO_OPENMP=1` builds without OpenMP. At runtime,
`SVGRASTER_PURE=1`, `Renderer(native=False)` or `with svgraster.pure_python():`
selects the numpy fallbacks.

## Layout

| Path | Technology | Role |
| --- | --- | --- |
| `svgraster/dom/` | Python | XML loading (`xml.etree`), CSS cascade, inheritance, colors, units, transforms |
| `svgraster/parse/` | Python | path data, basic shapes, arc/Bezier flattening, `viewBox`/`preserveAspectRatio` |
| `svgraster/_scanline.c` + `_native/scanline_core.h` | CPython C API | anti-aliased nonzero/evenodd polygon coverage |
| `svgraster/_paint.pyx` | Cython (`embedsignature`, `binding`) | gradient ramps, linear/radial gradients, spread methods |
| `svgraster/_pattern.pyx` | Cython | pattern tiling, sRGB/linearRGB conversion |
| `svgraster/_filters.cpp` + `_native/filters_*.hpp` | pybind11 | filter primitives |
| `svgraster/_composite.cpp` + `_native/stroke.hpp` | nanobind | Porter-Duff, coverage painting, masks, pixel conversion, stroking and dashing |
| `svgraster/_jit.py` | numba (optional) | supersampling downscale, unpremultiply |
| `svgraster/raster/`, `svgraster/filters/` | Python | dispatch to native layers and the numpy fallbacks |
| `svgraster/render/` | Python | renderer, paint servers, clip/mask, markers, filter chains, text |
| `svgraster/io/` | Python | PNG/PPM/npy writers |

What each binding demonstrates:

- **`_scanline` (C API).**
  - `METH_FASTCALL` functions with `__text_signature__` docstrings:
    `fill_polygons($module, out, polygons, rule=0, samples=4, /)` and
    `polygon_area`.
  - Functions with plain docstrings: `clamp_unit`, `coverage_sum` and
    `version`.
  - A `Rasterizer` type that can be subclassed. It has methods, `width` and
    `height` read-only getsets, a writable `samples` getset, the `from_shape`
    classmethod, and it exports its float32 coverage through the buffer
    protocol.
- **`_paint` (Cython, `embedsignature=True, binding=True`).**
  - Functions written with `cpdef`: `linear_gradient`, `radial_gradient` and
    `clamp_focal`.
  - The `GradientLUT` cdef class, with `size`, `linear_rgb` and `table`
    properties and the `cpdef` methods `sample` and `fill_linear`.
  - `prange` over typed memoryviews.
- **`_pattern` (Cython, default directives).**
  - Functions `pattern_fill`, `srgb_to_linear` and `linear_to_srgb`.
  - The `PatternTile` cdef class, with properties and a `cpdef fill` method.
  - `prange`.
- **`_filters` (pybind11).**
  - Eight `py::enum_` types, including `BlendMode` and `CompositeOperator`.
  - Two classes with several constructors:
    - `TransferFunction` can be identity, table/discrete, linear or gamma.
    - `LightSource` can be distant, point or spot.
    - Both use `def_property`, `def_property_readonly` and `def_readwrite`.
  - Overloaded `gaussian_blur` and `flood`.
  - Keyword arguments and defaults throughout.
  - `py::array_t` for inputs and outputs, with the GIL released and OpenMP
    loops.
- **`_composite` (nanobind).**
  - `nb::ndarray` with shape and contiguity constraints.
  - An overloaded `paint_coverage` (solid color or paint image).
  - `nb::kw_only` on `over`, `to_uint8`, `to_float32` and `stroke`.
  - `nb::sig` on `stroke` and one `paint_coverage` overload.
  - `nb::enum_` types `LineJoin` and `LineCap`.
  - Returns lists of arrays that own their memory.
- **Python-level forwarding.**
  - `raster.Rasterizer` subclasses the compiled `Rasterizer` and forwards
    `**kwargs` to the compiled constructor.
  - `raster.GradientLUT` subclasses the Cython class the same way.
  - `raster.make_rasterizer(...)` and `filters.blur(img, std, **kwargs)`
    forward `**kwargs` into compiled callables.

## Anti-aliasing

Coverage is exact along x: covered spans are integrated per pixel. Along y it
is supersampled with `antialias` sub-scanlines per row (16 by default).
`supersample=N` also renders at N times the size and box-filters down, using
numba when it is available. This smooths paint-server and filter edges.

## SVG 1.1 coverage

Supported:

- **Structure:**
  - `svg` (nested viewports with clipping), `g`, `defs`, `use` (with
    referenced content re-styled from the `use`), `symbol`, `switch` (first
    child), `a` (rendered as a group).
  - `viewBox` and every `preserveAspectRatio` mode.
  - `display`, `visibility`, `opacity`.
- **Shapes:**
  - `rect` (including `rx`/`ry`), `circle`, `ellipse`, `line`, `polyline`,
    `polygon`.
  - `path` with every command, including arcs, implicit commands and
    shorthand curves.
  - Path-data error recovery: the path renders up to the first error.
- **Fill and stroke:**
  - `fill-rule` nonzero/evenodd.
  - `fill-opacity`, `stroke-opacity`.
  - `stroke-width`, `stroke-linejoin` (miter/round/bevel), `stroke-linecap`
    (butt/round/square), `stroke-miterlimit`, `stroke-dasharray`,
    `stroke-dashoffset`.
  - Zero-length subpaths draw round or square dots.
- **Styling:**
  - Presentation attributes, `style` attributes and `<style>` sheets.
    Selectors can be type, class, id or universal, combined with descendant
    (space) or child (`>`) combinators, and `!important` is honoured.
  - `inherit` and property inheritance.
  - Named colors (all 147), `#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`,
    `rgb()`/`rgba()` with numbers or percentages, `hsl()`/`hsla()`,
    `currentColor`, `transparent`.
- **Units:** `px`, `pt`, `pc`, `mm`, `cm`, `in`, `em`, `ex` and `%`, with
  percentages resolved against the nearest viewport. `dpi` scales the output.
- **Transforms:** `matrix`, `translate`, `scale`, `rotate` (with a centre),
  `skewX`, `skewY`.
- **Gradients:**
  - Linear and radial, including the focal point.
  - `gradientUnits` and `gradientTransform`.
  - `spreadMethod` pad, reflect and repeat.
  - Inheritance of attributes and stops through `href`.
  - `color-interpolation: linearRGB`.
- **Patterns:** `patternUnits`, `patternContentUnits`, `patternTransform`,
  `viewBox` and `href` inheritance.
- **Clipping and masking:**
  - `clipPath` in either unit system, with `clip-rule`, nested `clip-path`,
    and `use` and `text` children.
  - `mask` with `maskUnits`, `maskContentUnits` and the mask region.
- **Markers:** `marker-start`, `marker-mid` and `marker-end` (plus the
  `marker` shorthand), `orient="auto"` and fixed angles, `markerUnits`,
  `viewBox`, `refX`/`refY`, and viewport clipping.
- **Filters:**
  - Filter region (`filterUnits`), `primitiveUnits`, primitive subregions,
    named results.
  - Inputs `SourceGraphic` and `SourceAlpha`.
  - `color-interpolation-filters` (linearRGB by default, or sRGB).
  - Primitives: `feGaussianBlur`, `feOffset`, `feFlood`, `feBlend` (all 16
    modes from Compositing and Blending), `feComposite` (over, in, out, atop,
    xor, arithmetic, lighter), `feColorMatrix` (all four types),
    `feComponentTransfer` (identity, table, discrete, linear, gamma),
    `feMorphology`, `feConvolveMatrix` (all edge modes, `preserveAlpha`),
    `feTile`, `feMerge`, `feTurbulence` (the reference algorithm, with
    stitching), `feDisplacementMap`, `feDiffuseLighting` and
    `feSpecularLighting` (distant, point and spot lights).
  - Also `feDropShadow` from Filter Effects 1.
- **Text:**
  - Built-in single-stroke font: A-Z, 0-9 and common punctuation. Lowercase
    letters are drawn as small capitals.
  - `text` and `tspan`, with the first `x`/`y`/`dx`/`dy` value.
  - `font-size`, a bold weight, `text-anchor`.
  - Glyphs are painted with the `fill` paint.

Gaps and approximations:

- **Not rendered:**
  - `image`, `foreignObject` and SVG fonts.
  - Animation (SMIL) and scripting.
  - `feImage`.
  - The `BackgroundImage`, `BackgroundAlpha`, `FillPaint` and `StrokePaint`
    inputs, which become transparent.
- **Text:**
  - No real fonts: `font-family` and `font-style` are ignored.
  - Text `stroke` is ignored.
  - Not supported: `textPath`, per-glyph position lists, `rotate`,
    `letter-spacing`, `textLength`.
  - `xml:space="preserve"` is ignored, so whitespace always collapses.
- **CSS:** attribute selectors, pseudo-classes, sibling combinators and
  `@media`/`@import` are ignored.
- **`switch`** ignores conditional attributes.
- **Filters:**
  - `feOffset` shifts by whole pixels.
  - `feDisplacementMap` and pattern tiles sample the nearest pixel.
  - `kernelUnitLength` and `filterRes` are ignored.
  - Lighting normals replicate edge pixels instead of using the spec's edge
    kernels.
  - The `feSpecularLighting` result is treated as premultiplied.
  - A primitive with no explicit subregion uses the whole filter region.
- **Stroking:**
  - Round joins on turns under 0.25 rad are drawn as bevels. The difference
    is under 1% of the half-width.
  - The first and last dashes of a closed path are not merged.
  - `vector-effect` (SVG 2) is not supported.
- **Masks:** luminance is computed from sRGB values, as browsers do. `mask-type`
  is not supported.
- **Error handling:** a reference to a missing clip, mask or filter is ignored
  and the element renders without it. SVG 1.1 would treat the element as in
  error.
- **Curve accuracy:** curves are flattened to `tolerance` device pixels (0.1 by
  default), which slightly shrinks the area of curved shapes.

## Tests

```
cd demos/svgraster
../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

The suite covers:

- Native against fallback output, with `allclose`, for every layer and every
  filter primitive.
- Known-pixel checks for shapes, fill rules, gradients, patterns,
  clipping/masking, markers and each filter.
- The coverage-sum-equals-area property.
- Parser cases.
- The CLI writing PNG, PPM and `.npy` files.
- A subprocess run with every native module (and numba) blocked, whose output
  is compared with the native render.
