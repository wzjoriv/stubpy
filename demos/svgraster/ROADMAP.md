# svgraster roadmap

A critical review of svgraster 0.1, written as if it had users, followed by
the prioritised work list. Items move to **Done** as they land; deferred
work lives in **Later** with the reason.

## Review of 0.1

### User experience and API

- `render()` takes markup, bytes or a path, but nothing else. Code that
  builds documents with an object model (anything with `__svg__()` or
  `to_string()`) has to serialise by hand first.
- Relative references (`<image href="logo.png">`, `@font-face url(...)`)
  have no base directory, because `Document.parse` forgets where the file
  came from. Markup strings have no way to supply one.
- There is no notion of time. Animated documents render their base value,
  and there is no frame or video API.
- `Renderer.render` is the only entry point for a frame. A caller that wants
  many frames re-parses the document every time.
- Errors are mostly honest (`ValueError` for malformed XML, bad sizes, bad
  colors), but the messages do not say which element or attribute failed,
  and missing references silently render nothing.

### CLI

- One flat command. It cannot render animation, has no benchmark, and
  `--backends` is a flag rather than a subcommand.
- There is no way to point at extra font folders.
- A missing input file prints a Python-ish `OSError` message; acceptable but
  terse.

### Correctness and SVG 1.1 coverage

Ordered by how visible the gap is in real files:

1. **Text is a toy.** A built-in stroke font with small caps for lowercase.
   `font-family`, `font-style`, kerning, `textPath`, per-glyph positions,
   `rotate`, `letter-spacing`, `word-spacing`, `baseline-shift`,
   `text-decoration`, stroked text and `xml:space` are all missing. Any SVG
   containing words looks wrong.
2. **`image` is not rendered.** Logos and screenshots disappear.
3. **Animation (SMIL) is ignored.** A large share of hand-made SVG uses
   `animate*`; the static frame is often a blank or mid-transition state.
4. **Filter inputs.** `BackgroundImage`, `BackgroundAlpha`, `FillPaint` and
   `StrokePaint` render transparent; `feImage` is missing.
5. **Filter accuracy.** `feOffset` snaps to whole pixels (visible jitter
   when scaled), `feDisplacementMap` and patterns sample the nearest pixel
   (aliasing), lighting uses replicated edges instead of the spec's edge
   kernels, `kernelUnitLength` is ignored, and a primitive without an
   explicit subregion uses the whole filter region instead of the union of
   its inputs' subregions.
6. **CSS.** No attribute selectors, no pseudo-classes, no sibling
   combinators; specificity is a single integer, so 10 classes outweigh an
   id.
7. **`switch`** ignores `systemLanguage`, `requiredFeatures` and
   `requiredExtensions`.
8. **SVG fonts** (`font`, `glyph`, `hkern`) are not used.

Scope decision: `foreignObject`, `script`, DOM events, `cursor` and
interactivity are web-only and are removed from scope. They are parsed and
ignored, and documented as such.

### Performance

- The C scanline filler is single-threaded even though OpenMP is available
  for the other layers.
- The nanobind compositing loops neither release the GIL nor use OpenMP.
- PNG decoding unfilters Sub/Average/Paeth rows byte by byte in Python.
- There is no benchmark, so none of this is measured.

### Packaging

- The nanobind runtime was compiled from its absolute site-packages path.
  Object files then landed in a deeply nested build directory, and on
  Windows the linker failed on long paths; the package fell back to numpy
  silently. Fixed by compiling the runtime through a package-local shim.
- OpenMP is optional with a silent retry; a serial build is easy to ship by
  accident. `backend_info()` reports it, but the CLI does not warn.
- Version 0.1.0 does not reflect the feature set.

## Prioritised work

P1 is the owner's explicit asks; P2 closes the remaining SVG 1.1 gaps; P3 is
polish.

| # | Priority | Item |
| --- | --- | --- |
| 1 | P1 | TrueType/OpenType parser: `cmap`, `glyf`/`loca` with composites, `hmtx`/`hhea`, `head`, `maxp`, `name`, `OS/2`, `post`, `kern` and `GPOS` pair kerning, CFF outlines |
| 2 | P1 | Font discovery (Windows, macOS, Linux folders, user files and folders), family/weight/style matching with generic families and fallback |
| 3 | P1 | `@font-face` with local `src: url(...)`; SVG fonts (`font`, `glyph`, `missing-glyph`, `hkern`) |
| 4 | P1 | Text layout: anchors per text chunk, `x`/`y`/`dx`/`dy`/`rotate` lists, `letter-spacing`, `word-spacing`, `textLength`, `textPath`, `baseline-shift`, `text-decoration`, stroked text, `xml:space`; the stroke font only as the last fallback |
| 5 | P1 | `image`: data URIs and local files; PNG (all color types, bit depths, interlacing) and baseline JPEG decoders; nested SVG images |
| 6 | P1 | `feImage`; `BackgroundImage`/`BackgroundAlpha` with `enable-background`; `FillPaint`/`StrokePaint` |
| 7 | P1 | Sub-pixel `feOffset`; bilinear `feDisplacementMap` and patterns; spec edge kernels for lighting; `kernelUnitLength` |
| 8 | P1 | CSS attribute selectors, `:first-child`, `:lang()`, `:link`, sibling combinators, proper specificity |
| 9 | P1 | SMIL: `animate`, `set`, `animateColor`, `animateTransform`, `animateMotion` + `mpath`; timing, `calcMode` linear/discrete/paced/spline, `additive`/`accumulate` |
| 10 | P1 | `render(svg, time=t)`, `render_animation(...)` through ffmpeg, `frames()` iterator, `animate` CLI subcommand |
| 11 | P1 | Duck-typed sources (`__svg__()`, `to_string()`), svgwriter interop tests, a frame callable for animation hooks |
| 12 | P1 | OpenMP in the scanline and compositing layers, GIL released in native loops, `bench` subcommand |
| 13 | P1 | Spread new native code across the C API, Cython, pybind11, nanobind and numba layers |
| 14 | P2 | `switch` conditional attributes; default primitive subregions; base directory for relative references |
| 15 | P3 | Clearer error messages; CLI subcommands; `--font-dir`; version bump |

## Done

- **Packaging:** the nanobind runtime is compiled through a package-local
  shim (the long-path link failure is gone); OpenMP is enabled for five
  layers; new modules are registered in `setup.py`, `backend_info()` and the
  package data; version 0.2.0.
- **1-3 Fonts.** `svgraster.fonts` parses TrueType (`glyf`, simple and
  composite glyphs) and CFF (Type 2 charstrings, subroutines, CID-keyed)
  outlines; `cmap` 0/4/6/12; `head`, `hhea`, `hmtx`, `maxp`, `name`, `OS/2`,
  `post`; `kern` format 0 and `GPOS` pair kerning; TTC collections. Fonts are
  discovered in the Windows, macOS and Linux folders, `SVGRASTER_FONT_PATH`,
  user files and folders, and matched by family list, generic family, CSS
  weight order and style, with synthetic bold/oblique, per-character system
  fallback and the stroke font last. `@font-face` (`url()`, `data:`,
  `local()`), `font-face` elements and SVG fonts (with ligatures and `hkern`)
  are supported.
- **4 Text layout:** chunks and anchors, position and rotation lists,
  kerning, letter and word spacing, `textLength`/`lengthAdjust`, `textPath`,
  `baseline-shift`, `dominant-baseline`/`alignment-baseline`, decorations,
  stroked text, synthetic bold, `xml:space`, `tref`, the `font` shorthand.
- **5 Images:** a PNG decoder for every color type and depth, `tRNS`, `gAMA`
  and Adam7; a baseline JPEG decoder (any sampling factors, restart
  intervals); SVG images; `preserveAspectRatio`, bilinear and nearest
  sampling; `data:` URIs and local files.
- **6 Filter inputs:** `feImage` (files, `data:` URIs, element references),
  `BackgroundImage`/`BackgroundAlpha` with `enable-background="new"`,
  `FillPaint`/`StrokePaint`.
- **7 Filter accuracy:** bilinear sub-pixel `feOffset`, bilinear
  `feDisplacementMap` and patterns, the spec's edge kernels for lighting,
  `kernelUnitLength`, `filterRes`, filter `href` inheritance. Default
  primitive subregions use the filter region (Filter Effects 1), which the
  conformance references confirm.
- **8 CSS:** attribute selectors, structural and `:lang()` pseudo-classes,
  `+`/`~` combinators, `(a, b, c)` specificity, `@media all|screen`,
  `@import` and `<?xml-stylesheet?>` with local files, `@font-face`, system
  colors.
- **9-10 Animation:** SMIL timing (clock values, begin lists, syncbases,
  repeats, freeze), values (`from`/`to`/`by`, `values`, `keyTimes`,
  `keySplines`, four calc modes), `additive`/`accumulate`, the sandwich
  model, `animateMotion` with `mpath` and `rotate`. `render(time=)`,
  `snapshot()`, `timeline()`, `frames()`, `frame_renderer()`,
  `render_animation()` (ffmpeg pipe for MP4/MOV/MKV/WebM/GIF/APNG; PNG
  sequences and `.npy` stacks without it; `FFmpegNotFoundError` explains the
  alternatives), `animate` subcommand.
- **11 Interop:** sources with `__svg__()`/`to_string()`, gzip (`.svgz`)
  input, `render_frame(document, seconds)` for animation hooks, svgwriter
  round-trip tests including its frame hook.
- **12 Performance:** band-parallel OpenMP scanline with the GIL released;
  OpenMP and GIL release in all nanobind compositing loops; the GIL is now
  released in the pybind11 offset, displacement and resampling loops too
  (blur, blend, morphology, convolution, turbulence and lighting already
  released it); Cython PNG unfiltering and
  JPEG entropy decoding; `bench` subcommand (native vs numpy).
- **13 Native spread:** C API `_glyf` module and scanline `set_num_threads`;
  Cython `_codec` (`cpdef enum`, cdef class, struct bit reader) and
  `sample_image`; pybind11 `ResampleFilter`, `resample` (keyword-only) and
  an `offset` overload; nanobind `FramePacker` and `PixelFormat`; numba
  `premultiply_u8` and `resample`.
- **14** `switch` and conditional attributes everywhere; `use` of elements in
  other local documents (their own paint servers resolve there); `use` of a
  nested `svg` keeps its `x`/`y`; foreign-namespace elements and attributes
  are ignored; `base_dir=` for markup; forced output sizes letterbox the
  `viewBox`.
- **15** CLI subcommands (`render`, `animate`, `bench`, `fonts`, `backends`,
  `conformance`) with the 0.1 flat form still working; `--font-dir`;
  messages that name the failing file or keyword.
- **Conformance:** `python -m svgraster conformance` and the
  `scripts/dev.py svgraster fetch-suite` downloader (developer tooling in
  `scripts/demo_tools/svgraster.py`).

### W3C SVG 1.1 SE conformance

434 tests in scope (92 excluded: 46 SVG DOM, 24 interactivity, 20 scripting,
2 `foreignObject`). Pass rule: at most 1% of pixels differ by more than
64/255 after a 3x3 box blur, within one pixel of the reference.

| Chapter | First run | After fixes |
| --- | ---: | ---: |
| animate | 25/74 | 55/74 |
| color | 3/6 | 3/6 |
| conform | 2/2 | 2/2 |
| coords | 28/28 | 28/28 |
| filters | 22/42 | 32/42 |
| fonts | 9/17 | 9/17 |
| imp | 0/1 | 0/1 |
| linking | 10/12 | 10/12 |
| masking | 15/17 | 15/17 |
| metadata | 1/1 | 1/1 |
| painting | 29/31 | 29/31 |
| paths | 19/19 | 19/19 |
| pservers | 28/33 | 29/33 |
| render | 7/8 | 7/8 |
| shapes | 22/22 | 22/22 |
| struct | 28/48 | 37/48 |
| styling | 9/17 | 10/17 |
| text | 25/54 | 25/54 |
| types | 1/2 | 1/2 |
| **Total** | **283/434 (65.2%)** | **334/434 (77.0%)** |

The first run was taken after the P1 work above; the fixes it drove were:
rendering animated tests at the end of their timeline (the references show
final states), filter-region default subregions, a bounding box for `image`
(filters on images), `FillPaint` opacity, external `use` references with
per-document resolution, `<?xml-stylesheet?>` and `@import`, PNG `gAMA`,
system colors, the pattern paint fallback, nested `svg` positions under
`use`, SVG images without a `viewBox`, foreign namespaces, and letterboxed
forced sizes.

Several remaining failures are not renderer bugs. 41 of the 100 failing
tests draw the suite's red "DRAFT" watermark (about 5% of the image). Some
reference PNGs include it and some predate it, so the harness leaves it in
place rather than guess; stripping it gained 56 tests and lost 21. A few
references show the failure state (for example `struct-use-06-b`,
`styling-pres-04-f`), and some tests are newer revisions than their PNGs.

## Later

- **Complex text shaping** (GSUB ligatures and contextual forms), **bidi**
  and **vertical text** (`writing-mode: tb`, `glyph-orientation-*`). Latin,
  Greek and Cyrillic are correct; Arabic and Indic are not. This is the main
  reason the `text` chapter stays at 46%.
- **SVG font refinements:** glyph `lang`/`orientation`/`arabic-form`
  selection, font-defined baselines (`alphabetic`, `hanging`,
  `mathematical` on `font-face`) used by the `fonts` and `text-align` tests.
- **Hinting.** TrueType instructions are ignored; glyphs are unhinted with
  exact anti-aliasing.
- **JPEG:** progressive, arithmetic, 12-bit and CMYK; EXIF orientation; ICC
  profiles (`color-profile`, `icc-color` fall back to sRGB).
- **WOFF/WOFF2** containers (WOFF needs only zlib; WOFF2 needs Brotli, which
  is not in the standard library).
- **Remote URLs** for images, fonts and documents are refused on purpose.
- **SMIL** `min`, `max`, `restart`, and event, `repeat(n)` and `accessKey`
  timing (events are out of scope).
- **CSS** `:not()`, namespaced selectors, `@namespace`.
- **GIL release** in the remaining short pybind11 loops (composite, color
  matrix, component transfer, flood, tile, merge).
- **`feSpecularLighting`** output premultiplication, and closing the
  remaining `filters-conv`/`filters-light` differences.
