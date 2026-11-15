# svgraster

Render SVG 1.1 documents into numpy arrays (`H x W x 4` RGBA, `uint8` or
`float32`): shapes, paint servers, clipping and masking, markers, every
filter primitive, text with real TrueType/OpenType and SVG fonts, raster and
SVG images, and SMIL animation, rendered frame by frame or straight to video.

The only runtime dependency is numpy. Fonts, PNG and JPEG are decoded by
svgraster itself. The hot paths are native, and each native layer uses a
different way of writing a compiled Python extension (CPython C API, Cython,
pybind11, nanobind, numba). Every layer has a numpy fallback, so the package
works unbuilt, and the tests compare every native layer against its
fallback.

```python
import svgraster

img = svgraster.render("drawing.svg")                         # uint8, straight alpha
img = svgraster.render(markup, width=512, background="white", dtype="float32")
img = svgraster.render(drawing)                               # any object with __svg__() or to_string()
frame = svgraster.render("spinner.svg", time=1.25)            # SMIL evaluated at 1.25 s
svgraster.render_animation("spinner.svg", "spinner.mp4", fps=30)   # needs ffmpeg
svgraster.render_animation("spinner.svg", "frames/f_%04d.png", fps=12)  # no ffmpeg needed

r = svgraster.Renderer(antialias=8, supersample=2, threads=4)
img = r.render(b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>")
svgraster.add_font_path("~/my-fonts")                         # extra fonts for every render
svgraster.backend_info()                                      # which native layers are built
```

## Command line

```
python -m svgraster render in.svg -o out.png [--width N] [--height N] [--dpi 96] [--time S]
                           [--background white] [--antialias 16] [--supersample 1]
                           [--threads N] [--float] [--pure] [--font-dir PATH ...]
python -m svgraster animate in.svg -o out.mp4 --fps 30 [--duration S] [--start S] [--ffmpeg PATH]
python -m svgraster bench [FILES ...] [--size 512] [--repeat 3] [--threads N] [--compare] [--json]
python -m svgraster fonts [--match "Georgia, serif" --weight bold --italic] [--dirs] [--font-dir PATH]
python -m svgraster backends
python -m svgraster conformance [--suite DIR] [--filter PATTERN] [--report out.md] [--failures]
```

`python -m svgraster in.svg -o out.png` (no subcommand) still renders, and
`--backends` still prints the backend report. Still images are written as
`.png`, binary `.ppm` (composited over white) or `.npy`. `animate` writes
`.mp4`, `.mov`, `.mkv`, `.webm`, `.gif` and `.apng` through ffmpeg, or a
`.npy` frame stack or a `%`-pattern PNG sequence without it.

## Text and fonts

`svgraster.fonts` parses fonts itself:

- **TrueType outlines:** `glyf`/`loca`, simple and composite glyphs (scaled,
  2x2 and point-matched components), quadratic contours turned into paths.
- **OpenType CFF outlines:** Type 2 charstrings with local and global
  subroutines, hint masks, flex, and CID-keyed fonts (`FDArray`/`FDSelect`).
- **Tables:** `cmap` (formats 0, 4, 6 and 12, plus symbol fonts), `head`,
  `hhea`, `hmtx`, `maxp`, `name`, `OS/2`, `post`, `kern` (format 0) and
  `GPOS` pair kerning (formats 1 and 2, through extension lookups).
  Collections (`.ttc`) expose every face.
- **Discovery:** the system font folders (Windows, macOS and Linux),
  `SVGRASTER_FONT_PATH`, `add_font_path()`, `--font-dir`, and
  `FontDatabase([...])`. Faces are described from their `name`/`OS/2`
  tables without a full parse, and parsed on first use.
- **Matching:** CSS-style matching of `font-family` lists, generic families
  (`serif`, `sans-serif`, `monospace`, `cursive`, `fantasy`), weights (the
  CSS fallback order) and italic/oblique, with synthetic bold and oblique
  when no face matches. Characters missing from every requested family fall
  back to system faces that cover them, and finally to a built-in stroke
  font.
- **Document fonts:** `@font-face` rules with `src: url(...)` (local files and
  `data:` URIs) or `local(...)`, `font-face` elements with `font-face-uri`
  and `font-face-name`, and SVG fonts (`font`, `glyph`, `missing-glyph`,
  `hkern`, multi-character ligature glyphs), in the document or in another
  local SVG file.

Text layout supports `text`, `tspan`, `tref`, `altGlyph` (as `tspan`) and
`textPath`:

- `x`/`y`/`dx`/`dy`/`rotate` lists, absolute positions starting new text
  chunks, `text-anchor` per chunk.
- Pair kerning, `kerning`, `letter-spacing` and `word-spacing`.
- `textLength` with `lengthAdjust` (`spacing` and `spacingAndGlyphs`).
- `baseline-shift` (`sub`, `super`, percentages, lengths),
  `dominant-baseline` and `alignment-baseline` (`middle`, `central`,
  `hanging`, `mathematical`, `text-before-edge`, `text-after-edge` and
  aliases).
- `textPath` with `startOffset` (length or percentage); glyphs off the ends of
  the path are not drawn.
- `text-decoration` (underline, overline, line-through) painted with the
  decorating element's fill and stroke, using the font's metrics.
- Stroked text, paint servers on text (the bounding box is the union of
  glyph cells), text in `clipPath`.
- `xml:space` (`default` and `preserve`), and the `font` shorthand.
- Bidirectional text: the Unicode Bidirectional Algorithm (UAX #9) with
  explicit embeddings, overrides and isolates, bracket pairs and mirroring;
  `direction` and `unicode-bidi`. `text-anchor` applies to the visual run, and
  `x`/`y`/`dx`/`dy`/`rotate` to logical characters.
- Complex shaping with OpenType `GSUB` (lookup types 1-8) and `GPOS` (types
  1-8: single, pair, cursive, mark-to-base, mark-to-ligature, mark-to-mark,
  contextual, chained), script/language/feature selection and GDEF classes.
  Shapers: default (`ccmp`, `locl`, `rlig`, `liga`, `clig`, `calt`, `kern`,
  `mark`, `mkmk`, ...), Arabic (joining analysis, `isol`/`init`/`medi`/`fina`,
  lam-alef, presentation-form fallback), Hebrew (marks), Devanagari (syllables,
  reph and pre-base matra reordering) and Thai (sara am).
- Basic vertical text (`writing-mode: tb`, `glyph-orientation-vertical`,
  `vmtx` advances).

Unicode tables (scripts, joining types, Indic categories, brackets, mirroring)
are generated into `svgraster/shaping/_ucd.py` by
`python scripts/dev.py demos svgraster gen-unicode`, which also downloads
`BidiCharacterTest.txt`; the bidi implementation passes all 91,707 cases.

Glyph outlines are flattened and filled by the same native scanline as every
other shape.

## Images

`image` draws PNG, JPEG and SVG from `data:` URIs or local files (paths and
`file:` URLs relative to the document; `Document.parse(..., base_dir=...)` or
`render(..., base_dir=...)` for markup). Remote URLs are refused with a
warning.

- **PNG:** every color type and bit depth (1 to 16), palettes, `tRNS`, `gAMA`,
  and Adam7 interlacing. Scanline unfiltering is Cython.
- **JPEG:** baseline Huffman, 8-bit, grayscale and YCbCr with any sampling
  factors, restart markers and the Adobe transform flag. Entropy decoding is
  Cython; the IDCT is vectorised numpy.
- **SVG:** rendered as a nested document; without a `viewBox` it is drawn
  into the image viewport unscaled.
- `preserveAspectRatio` (all modes, `meet` and `slice`), bilinear sampling,
  and `image-rendering: optimizeSpeed` for nearest-neighbour.

## Animation

SMIL is evaluated at a time: `animate`, `set`, `animateColor`,
`animateTransform` and `animateMotion` (with `path`, `mpath`,
`values`/`from`/`to`/`by`, `keyPoints`, and `rotate` as `auto`,
`auto-reverse` or an angle).

- **Timing:** clock values in every form, `begin` lists, syncbases
  (`id.begin+1s`, `id.end`), `end`, `dur`, `repeatCount`, `repeatDur`, and
  `fill` (`freeze`/`remove`). Event-based begins never start.
- **Values:** `values`, `from`/`to`/`by`, to-animations from the underlying
  value, `keyTimes`, `keySplines`, and `calcMode` `discrete`, `linear`,
  `paced` and `spline`. Numbers, lengths, lists, path data, colors and
  transforms are interpolated when their shapes match.
- **Composition:** the SMIL sandwich model (begin time, then document
  order), `additive="sum"` and `accumulate="sum"`. CSS properties are
  animated above the cascade; XML attributes replace the attribute.

`svgraster.snapshot(doc, t)` returns the animated document, `timeline(doc)`
its natural length, `frames()` yields `(t, image)` pairs, and
`frame_renderer(svg)` returns `f(t) -> image` with the document parsed once.
`render_frame(document, seconds)` matches the `(document, seconds) -> RGBA`
renderer hook that animation libraries call, for example
`renderer="svgraster:render_frame"`.

## Building

```
cd demos/svgraster
python setup.py build_ext --inplace
```

The build runs single-threaded. Every extension is optional. A missing
toolchain or a failed compile is reported and skipped, and that layer falls
back to numpy. OpenMP (`/openmp` on MSVC, `-fopenmp` elsewhere) is enabled for
the scanline, paint, pattern, filter and compositing layers, and each one is
retried without it if that fails.

- `SVGRASTER_SKIP=capi,cython,pybind11,nanobind` skips layers.
- `SVGRASTER_NO_OPENMP=1` builds without OpenMP.
- At runtime, `SVGRASTER_PURE=1`, `Renderer(native=False)` or
  `with svgraster.pure_python():` selects the numpy fallbacks.
- `svgraster.backend_info()` and `python -m svgraster backends` report which
  layers are built and which use OpenMP.

## Layout

| Path | Technology | Role |
| --- | --- | --- |
| `svgraster/dom/` | Python | XML loading with namespaces, CSS cascade and selectors, colors, units, transforms, external documents |
| `svgraster/parse/` | Python | path data, basic shapes, arc/Bezier flattening, `viewBox`/`preserveAspectRatio` |
| `svgraster/fonts/` | Python | sfnt tables, `glyf` and CFF outlines, kerning, discovery, matching, SVG fonts, stroke font |
| `svgraster/render/` | Python | renderer, paint servers, clip/mask, markers, filter chains, images |
| `svgraster/render/text/` | Python | text content, document fonts, bidi runs, layout, `textPath`, decorations |
| `svgraster/shaping/` | Python | bidi, script itemization, OpenType GSUB/GPOS, script shapers |
| `svgraster/animation/` | Python | SMIL timing, values, motion, snapshots, frames and video |
| `svgraster/io/` | Python | PNG and JPEG decoders, PNG/PPM/npy writers, resource loading |
| `svgraster/cli/` | Python | the `python -m svgraster` subcommands |
| `svgraster/_scanline.c` + `_native/scanline_core.h` | CPython C API | anti-aliased nonzero/evenodd coverage, band-parallel with OpenMP |
| `svgraster/_glyf.c` | CPython C API | TrueType simple-glyph decoding |
| `svgraster/_paint.pyx` | Cython (`embedsignature`, `binding`) | gradient ramps, linear/radial gradients, spread methods |
| `svgraster/_pattern.pyx` | Cython | pattern tiling and image resampling (bilinear), sRGB/linearRGB |
| `svgraster/_codec.pyx` | Cython (`embedsignature`, `cpdef enum`) | PNG unfiltering, JPEG entropy decoding, YCbCr conversion |
| `svgraster/_bidi.pyx` | Cython (`cdef enum`, `nogil`) | bidi weak, neutral and implicit resolution |
| `svgraster/_filters.cpp` + `_native/filters_*.hpp` | pybind11 | filter primitives and resampling |
| `svgraster/_composite.cpp` + `_native/stroke.hpp` | nanobind | Porter-Duff, coverage painting, masks, conversions, stroking, video frame packing |
| `svgraster/_jit.py` | numba (optional) | supersampling downscale, unpremultiply, premultiply, bilinear resize |

What each binding demonstrates:

- **`_scanline` (C API).**
  - `METH_FASTCALL` functions with `__text_signature__` docstrings:
    `fill_polygons($module, out, polygons, rule=0, samples=4, /)` and
    `polygon_area`; `METH_O` `set_num_threads`.
  - Functions with plain docstrings: `clamp_unit`, `coverage_sum` and
    `version`.
  - A subclassable `Rasterizer` type with methods, read-only and writable
    getsets, a classmethod and the buffer protocol.
  - The GIL is released while bands of rows are filled in parallel.
- **`_glyf` (C API).** `simple_glyph($module, data, offset, /)` returning a
  tuple and packed bytes from any buffer, `glyph_header`, integer constants.
- **`_paint` (Cython, `embedsignature=True, binding=True`).** `cpdef`
  functions, the `GradientLUT` cdef class with properties and `cpdef`
  methods, `prange` over typed memoryviews.
- **`_pattern` (Cython, default directives).** `pattern_fill` and
  `sample_image` (keyword-only `bilinear` and `repeat`), color-space
  conversion, the `PatternTile` cdef class, `prange`.
- **`_codec` (Cython, `embedsignature=True`).** `cpdef enum` types
  `PngFilter` and `TableClass`, the `HuffmanTable` cdef class with `public`,
  `readonly` and computed properties, a `CodecError` exception, a C struct
  bit reader under `nogil`, functions taking `const` memoryviews.
- **`_filters` (pybind11).**
  - Nine `py::enum_` types, including `BlendMode`, `CompositeOperator` and
    `ResampleFilter`.
  - `TransferFunction` and `LightSource` with several constructors,
    `def_property`, `def_property_readonly` and `def_readwrite`.
  - Overloaded `gaussian_blur`, `flood` and `offset` (two floats or a pair),
    `py::kw_only` on `resample`.
  - `py::array_t` inputs and outputs, the GIL released around OpenMP loops.
- **`_composite` (nanobind).**
  - `nb::ndarray` with shape and contiguity constraints, an overloaded
    `paint_coverage`, `nb::kw_only`, `nb::sig`.
  - `nb::enum_` types `LineJoin`, `LineCap` and `PixelFormat`.
  - The `FramePacker` class with `def_prop_ro`/`def_prop_rw` properties, a
    keyword-only constructor, `__repr__`, and a method returning `bytes`.
  - OpenMP loops with the GIL released.
- **`_jit` (numba).** `njit(nogil=True)` kernels with numpy twins.
- **Python-level forwarding.** `raster.Rasterizer` and `raster.GradientLUT`
  subclass compiled classes and forward `**kwargs`; `filters.blur` and
  `raster.make_rasterizer` forward `**kwargs` into compiled callables.

## Anti-aliasing

Coverage is exact along x: covered spans are integrated per pixel. Along y it
is supersampled with `antialias` sub-scanlines per row (16 by default).
`supersample=N` also renders at N times the size and box-filters down. This
smooths paint-server and filter edges. Images, patterns, displacement and
offsets are sampled bilinearly.

## SVG 1.1 coverage

Supported:

- **Structure:** `svg` (nested viewports with clipping), `g`, `defs`, `use`
  (including `file.svg#id` in other local documents), `symbol`, `switch`
  with `systemLanguage`, `requiredFeatures` and `requiredExtensions` (also on
  elements outside `switch`), `a`, `image`. `viewBox` and every
  `preserveAspectRatio` mode. `display`, `visibility`, `opacity`. Elements in
  foreign namespaces are ignored. `.svgz` input.
- **Shapes and paths:** every basic shape and path command, with error
  recovery. Fill rules, stroke joins, caps, miter limits, dashes, and dots for
  zero-length subpaths.
- **Styling:** presentation attributes, `style` attributes, `<style>` sheets,
  `<?xml-stylesheet?>` and `@import` of local CSS, `@media all|screen`,
  `!important`. Selectors: type, class, id, universal, attribute (`=`, `~=`,
  `|=`, `^=`, `$=`, `*=`), `:first-child`, `:last-child`, `:only-child`,
  `:nth-child()`, `:root`, `:empty`, `:link`, `:lang()`, and the descendant,
  child, `+` and `~` combinators, with `(id, class, type)` specificity.
  Dynamic pseudo-classes never match.
- **Colors and units:** named and system colors, hex, `rgb()`, `hsl()`,
  `currentColor`; every SVG length unit and percentages.
- **Paint servers:** linear and radial gradients (focal points, spread
  methods, `href` inheritance, linearRGB), patterns (with `href`
  inheritance; an empty pattern uses the paint fallback).
- **Clipping, masking, markers:** as in SVG 1.1.
- **Filters:** every primitive plus `feDropShadow`; `feImage` (files,
  `data:` URIs and element references); inputs `SourceGraphic`,
  `SourceAlpha`, `BackgroundImage` and `BackgroundAlpha` (from the nearest
  `enable-background="new"` ancestor), `FillPaint` and `StrokePaint`;
  sub-pixel `feOffset`; bilinear `feDisplacementMap`; the spec's edge kernels
  for lighting normals; `kernelUnitLength`; `filterRes`; filter `href`
  inheritance; `color-interpolation-filters`.
- **Text, fonts, images, animation:** see the sections above.

Out of scope: `foreignObject`, `script`, DOM events and interactivity,
`cursor`, and hyperlink activation. They are parsed and ignored.

Gaps and approximations:

- **Text:** no complex shaping (GSUB, contextual forms), no bidirectional
  reordering and no vertical text, so Arabic and Indic scripts and
  `writing-mode: tb` render incorrectly. TrueType hinting is not applied.
  `glyph-orientation-*` and the language selection of SVG font glyphs are
  ignored. A `textPath` uses the first subpath of its path.
- **Images:** progressive, arithmetic, 12-bit and CMYK JPEG are rejected with
  a clear error. ICC profiles and EXIF orientation are ignored.
- **Fonts:** WOFF and WOFF2 are not read.
- **Animation:** event-based and `accessKey` begins never start; `min`,
  `max` and `restart` are ignored.
- **Filters:** the `feSpecularLighting` result is treated as premultiplied.
- **Stroking:** round joins on turns under 0.25 rad are drawn as bevels (under
  1% of the half-width); the first and last dashes of a closed path are not
  merged.
- **Masks:** luminance is computed from sRGB values, as browsers do.
- **Error handling:** a reference to a missing clip, mask or filter is ignored
  and the element renders without it. Unloadable images and fonts produce a
  warning and are skipped.

## Conformance

`python -m svgraster conformance` scores renders against the W3C SVG 1.1
Second Edition test suite's reference PNGs. The suite is not shipped; the
developer command `python scripts/dev.py svgraster fetch-suite` downloads it
into `demos/svgraster/conformance/suite/` (git-ignored). Animated tests are
rendered at the end of their timeline. A test passes when at most 1% of
pixels, after a 3x3 box blur of both images, differ by more than 64/255 from
every reference pixel within one pixel. Scripting, DOM, interactivity and
`foreignObject` tests are excluded and listed in the report. See
`ROADMAP.md` for the current score.

## Tests

```
cd demos/svgraster
python -m pytest -q -p no:cacheprovider
```

The suite covers:

- Native against fallback output for every layer, every filter primitive,
  the band-parallel scanline, resampling, codecs and the glyph decoder.
- Known-pixel checks for shapes, paint servers, clipping and masking,
  markers, filters and their new inputs, images, and text.
- Font parsing on an installed system font (skipped when none is found),
  font matching, SVG fonts, and text metrics and layout.
- PNG and JPEG decoding against small fixtures and reference decodes.
- SMIL timing, interpolation, snapshots, frames and, when ffmpeg is on
  `PATH`, MP4 and GIF output.
- The CLI subcommands, and a conformance smoke test when the suite has been
  downloaded.
- Interop with svgwriter documents and its animation hook (skipped when it
  is not importable).
- A subprocess run with every native module (and numba) blocked, compared
  with the native render.
