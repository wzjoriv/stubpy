# svgwriter

Write SVG 1.1 documents from Python. Every SVG 1.1 element is a class whose
keyword arguments are its attributes, also available under a lowercase
alias (`svg.circle`, `svg.linear_gradient`). Documents and containers have
shortcut methods that build, add and return elements, and operators compose
shapes, paths, transforms and colors. A small parser reads SVG text back
into the same object model, so documents round-trip. The core is pure
standard library, Python 3.10+.

```python
import svgwriter as svg

doc = svg.Document(200, 120)
sky = doc.linear_gradient(svg.Stop(0, "lightskyblue"), svg.Stop(1, "white"), x2=0, y2=1)
shadow = doc % svg.drop_shadow(3, 3, blur=2)          # into <defs>, gives url(#id)

doc.rect(0, 0, 200, 120, fill=sky)
with doc.group(stroke="black", stroke_width=2, filter=shadow):
    doc.circle(60, 60, 30, fill="gold")
    doc.path(svg.PathBuilder().move_to(110, 90).arc_to(30, 30, 0, False, True, 170, 90).close(), fill="tomato")
doc.text("Hello", x=100, y=20, text_anchor="middle", font_family="sans-serif")

doc.save("hello.svg")
again = svg.Document.from_file("hello.svg")
assert again.to_string() == doc.to_string()
```

Python keywords map onto SVG names: `stroke_width` is `stroke-width`,
`view_box` is `viewBox`, `class_` is `class`, `in_` is `in`, `from_` is
`from`, `xlink_title` is `xlink:title` and `href` is `xlink:href`. Passing
an element where a reference is expected (`fill=gradient`, `href=symbol`)
writes `url(#id)` or `#id`, assigning an id if the element has none.

## Shortcuts

Every shortcut takes exactly the arguments of the class it is named after
and returns the new element.

| Goes to the insertion point | Goes into `<defs>` with an id |
| --- | --- |
| `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path`, `text`, `group`, `link`, `switch`, `use`, `image` | `linear_gradient`, `radial_gradient`, `pattern`, `clip_path`, `mask`, `marker`, `filter`, `symbol` |

They exist on `Document` and on every drawing container (`g`, `svg`,
`defs`, `symbol`, `switch`, `a`, `clipPath`, `mask`, `marker`,
`pattern`). Containers they return nest with `with`:

```python
with doc.clip_path() as round_clip:
    doc.circle(50, 50, 40)
with doc.group(clip_path=round_clip) as photo:
    photo.image("photo.png", 0, 0, 100, 100)
```

## Operators

| Expression | Result |
| --- | --- |
| `container += element`, `container += [a, b]` | append (`doc += ...` appends at the insertion point) |
| `a + b`, `a + [b, c]`, `[a, b] + c` | a new `<g>` holding them |
| `doc % element` | put *element* in `<defs>` once, return `url(#id)` |
| `doc %= element`, `doc %= [a, b]` | the same, keeping `doc` |
| `path1 + path2`, `path += "M0 0 h5"` | concatenated subpaths |
| `shape * transform`, `shape @ matrix`, `transform @ shape` | a `<path>` with the transform baked in (arcs stay arcs) |
| `a \| b`, `a & b`, `a - b`, `a ^ b` | union, intersection, difference, xor as a `<path>` (skia-python) |
| `path \|= other`, `path -= other`, `path *= t`, ... | in-place forms on `<path>` |
| `Transform.rotate(30) @ Transform.scale(2)`, `t @ (x, y)` | composition, point mapping |
| `Color + Color`, `color * 0.5`, `color / 2` | even mix, channel scaling |

Boolean operators work on any shape, on `PathData` or path text, and on
`<text>` through its glyph outlines; the result carries the left operand's
presentation attributes.

```python
ring = svg.circle(50, 50, 40, fill="teal") - svg.circle(50, 50, 25)
stencil = svg.rect(0, 0, 120, 50) - svg.text("Hi", x=10, y=40, font_size=40, font_family="Arial")
petal = svg.ellipse(50, 20, 10, 20)
flower = petal.union(*(petal * svg.Transform.rotate(a, 50, 50) for a in range(60, 360, 60)))
```

## Geometry with skia-python

`pip install 'svgwriter[ops]'` installs the one optional dependency,
skia-python. Everything else works without it; the features below raise
`svgwriter.MissingDependencyError` with the install command when it is
missing.

| Feature | API |
| --- | --- |
| Boolean operations | `a \| b`, `a & b`, `a - b`, `a ^ b`, `shape.union(*others)`, `svg.ops.combine(a, b, BooleanOp.XOR)` |
| Text to outlines | `svg.text_to_path("Hi", "Arial", 48)`, `text.to_path()`, `svg.ops.text_width(...)` |
| Simplify | `shape.simplified()`, `svg.ops.simplify(...)` |
| Stroke to path | `shape.stroked(width, cap=, join=, miter_limit=)` |
| Exact bounds | `shape.exact_bbox()` (curves, not samples) |
| Hit testing | `shape.contains_point(x, y)` (honours `fill-rule` and `transform`) |
| Length | `shape.total_length()`, `shape.point_at_length(d)`, `svg.ops.tangent_at_length(...)` |
| Rasterize | `svg.ops.rasterize(doc, scale=2)` returns PNG bytes |

Shape-to-path conversion (`shape.to_path()`) and baked transforms are pure
Python and always available.

## Animation to video

The SMIL elements (`animate`, `set`, `animateMotion`, `animateTransform`,
...) describe animation inside the SVG. To get a video or GIF,
`Document.render_animation` renders frames through a pluggable renderer and
pipes them to `ffmpeg`:

```python
doc = svg.Document(160, 160)
planet = doc.circle(130, 80, 8, fill="deepskyblue")

def orbit(document, seconds):
    planet.cx = 80 + 50 * math.cos(math.pi * seconds)
    planet.cy = 80 + 50 * math.sin(math.pi * seconds)

doc.render_animation("orbit.mp4", fps=30, duration=2, renderer="skia", update=orbit)
```

A renderer is any callable `renderer(document, seconds)` returning PNG
bytes or a `(height, width, 4)` uint8 RGBA array. There is no default;
`"skia"` is built in when skia-python is installed, `"module:function"`
imports one, and `svg.register_renderer("name")` registers your own. The
output extension picks the encoder (`.mp4`, `.gif`, `.webm`, `.mov`,
`.apng`). When ffmpeg is not on `PATH`, `FFmpegNotFoundError` is raised
before anything is rendered. `duration` defaults to the end of the
document's SMIL animations.

## Command line

```
python -m svgwriter shapes                         # list registered composite shapes
python -m svgwriter elements                       # list supported elements by category
python -m svgwriter draw star -o star.svg          # render a registered shape
python -m svgwriter format in.svg --compact        # parse and re-serialize
python -m svgwriter info in.svg                    # element counts
python -m svgwriter animate scene.py --fps 30 --out anim.mp4 --renderer skia
python -m svgwriter render scene.py -o frame.png --time 0.5      # skia-python
python -m svgwriter outline "Logo" --font Arial --size 64 -o logo.svg   # skia-python
```

A scene is an `.svg` file or a `.py` file defining `build()` returning a
`Document`, optionally `update(document, seconds)` and the defaults `FPS`,
`DURATION` and `RENDERER` (see `examples/orbit_scene.py`).

## Feature support

| Area | Support |
| --- | --- |
| Structure | `svg`, `g`, `defs`, `desc`, `title`, `metadata`, `symbol`, `use`, `image`, `switch`, `a`, `style`, `view` |
| Shapes | `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path`, with bounding boxes, areas and conversion to `<path>` |
| Path data | M/L/H/V/C/S/Q/T/A/Z, absolute and relative; parsing (implicit repeats, packed arc flags), normal and shortest serialization, conversion to absolute, normalization, subpaths, exact affine transforms (arcs included), arc endpoint-to-center conversion, `PathBuilder` |
| Text | `text`, `tspan`, `tref`, `textPath`, `altGlyph`, `altGlyphDef`, `altGlyphItem`, `glyphRef`; `text-decoration` flags; glyph outlines (skia) |
| Fonts | `font`, `glyph`, `missing-glyph`, `hkern`, `vkern`, `font-face`, `font-face-src`, `font-face-uri`, `font-face-format`, `font-face-name` |
| Paint servers | `linearGradient`, `radialGradient`, `stop`, `pattern` |
| Clipping and masking | `clipPath`, `mask`, `marker` |
| Filters | `filter` and all 16 primitives, `feFuncR/G/B/A`, `feMergeNode`, `feDistantLight`, `fePointLight`, `feSpotLight`; result chaining by object; ready-made `drop_shadow` and `glow` |
| Animation | `animate`, `set`, `animateMotion`, `mpath`, `animateColor`, `animateTransform`; `float("inf")` writes `indefinite`; rendering to mp4/gif/webm through ffmpeg |
| Color management | `color-profile`, `icc-color(...)` fallbacks |
| Attributes | every presentation attribute, `style` parsing and moving to and from attributes, `StyleSheet` for `<style>`; core, conditional-processing and XLink attributes |
| Values | lengths with all SVG units and conversion to user units; the 147 color keywords, `#rgb`, `#rrggbb`, `rgb()` with integers or percentages; paint with fallbacks; `viewBox`, `preserveAspectRatio`; transform lists with parsing, composition and matrix collapse |
| Geometry (skia-python) | boolean operations, simplify, stroke-to-path, exact bounds, hit testing, length and point-at-length, text outlines, rasterizing |
| Output | pretty or compact, number precision, XML declaration, DOCTYPE, escaping, to a string, a path, a text stream, streamed chunks or asynchronously; notebook display (`_repr_svg_`) |
| Input | `xml.etree` parser into the element classes; unknown and foreign-namespace content is kept; lenient, warning or strict modes |

Not covered: CSS selector matching and cascade, DTD validation, CDATA
sections (text is escaped instead), and browser scripting. `script`,
`foreignObject`, `cursor`, the `cursor` property and event attributes such
as `onclick` are not supported: setting them raises `ValueError`, and the
parser drops them (an error in strict mode).

## Layout

```
svgwriter/
  elements/      structure/, shapes/, text, fonts, paint, clip, filters/, animation,
                 container (+=, %, with), _factory (shortcuts), _geometry (operators)
  attributes/    names, length, viewbox, style, reference, descriptors, values
  path/          commands, parser, data, arc, builder, affine transforms
  transform/     matrix, ops, transform
  color/         color keywords, parsing, operators, paint
  io/            writer, parser, async helpers
  builder/       functional API, registered shapes, effects
  ops/           skia-python geometry: boolean, measure, text, render
  video/         frames, renderers, ffmpeg encoding
  cli/           command line
  aliases.py     lowercase element aliases
  document.py    Document with shortcuts and nesting
```

## Installing, tests and examples

```
pip install svgwriter            # core, no dependencies
pip install 'svgwriter[ops]'     # plus skia-python geometry
python -m pytest -q              # skia and ffmpeg tests skip when those are missing
python examples/basic_shapes.py /tmp/out
```
