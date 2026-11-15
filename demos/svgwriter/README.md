# svgwriter

Write SVG 1.1 documents from Python. Every SVG 1.1 element is a class whose
keyword arguments are its attributes, a functional API builds common pieces
in one call, and a small parser reads SVG text back into the same object
model, so documents round-trip. Pure standard library, Python 3.10+.

```python
import svgwriter as svg

doc = svg.Document(200, 120)
sky = doc.define(svg.LinearGradient.vertical("lightskyblue", "white"))
shadow = doc.define(svg.drop_shadow(3, 3, blur=2))

doc.add(svg.Rect(0, 0, 200, 120, fill=sky))
with doc.group(stroke="black", stroke_width=2, filter=shadow):
    doc.add(svg.Circle(60, 60, 30, fill="gold"))
    doc.add(svg.Path(svg.PathBuilder().move_to(110, 90).arc_to(30, 30, 0, False, True, 170, 90).close(), fill="tomato"))
doc.add(svg.Text("Hello", x=100, y=20, text_anchor="middle", font_family="sans-serif"))

doc.save("hello.svg")
again = svg.Document.from_file("hello.svg")
assert again.to_string() == doc.to_string()
```

Python keywords map onto SVG names: `stroke_width` is `stroke-width`,
`view_box` is `viewBox`, `class_` is `class`, `in_` is `in`, `from_` is
`from`, `xlink_title` is `xlink:title` and `href` is `xlink:href`. Passing
an element where a reference is expected (`fill=gradient`, `href=symbol`)
writes `url(#id)` or `#id`, assigning an id if the element has none.

## Command line

```
python -m svgwriter shapes                  # list registered composite shapes
python -m svgwriter elements                # list supported elements by category
python -m svgwriter draw star -o star.svg   # render a registered shape
python -m svgwriter format in.svg --compact # parse and re-serialize
python -m svgwriter info in.svg             # element counts
```

## Feature support

| Area | Support |
| --- | --- |
| Structure | `svg`, `g`, `defs`, `desc`, `title`, `metadata`, `symbol`, `use`, `image`, `switch`, `a`, `style`, `script`, `foreignObject`, `view`, `cursor` |
| Shapes | `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path`, with bounding boxes and areas |
| Path data | M/L/H/V/C/S/Q/T/A/Z, absolute and relative; parsing (implicit repeats, packed arc flags), normal and shortest serialization, conversion to absolute, normalization of shorthands, arc endpoint-to-center conversion, `PathBuilder` |
| Text | `text`, `tspan`, `tref`, `textPath`, `altGlyph`, `altGlyphDef`, `altGlyphItem`, `glyphRef`; `text-decoration` flags |
| Fonts | `font`, `glyph`, `missing-glyph`, `hkern`, `vkern`, `font-face`, `font-face-src`, `font-face-uri`, `font-face-format`, `font-face-name` |
| Paint servers | `linearGradient`, `radialGradient`, `stop`, `pattern` |
| Clipping and masking | `clipPath`, `mask`, `marker` |
| Filters | `filter` and all 16 primitives, `feFuncR/G/B/A`, `feMergeNode`, `feDistantLight`, `fePointLight`, `feSpotLight`; result chaining by object; ready-made `drop_shadow` and `glow` |
| Animation | `animate`, `set`, `animateMotion`, `mpath`, `animateColor`, `animateTransform`; `float("inf")` writes `indefinite` |
| Color management | `color-profile`, `icc-color(...)` fallbacks |
| Attributes | every presentation attribute, `style` parsing and moving to and from attributes, `StyleSheet` for `<style>`; core, conditional-processing, XLink and event attributes |
| Values | lengths with all SVG units and conversion to user units; the 147 color keywords, `#rgb`, `#rrggbb`, `rgb()` with integers or percentages; paint with fallbacks; `viewBox`, `preserveAspectRatio`; transform lists with parsing, composition and matrix collapse |
| Output | pretty or compact, number precision, XML declaration, DOCTYPE, escaping, to a string, a path, a text stream, streamed chunks or asynchronously |
| Input | `xml.etree` parser into the element classes; unknown and foreign-namespace content is kept; lenient, warning or strict modes |

Not covered: CSS selector matching and cascade, rendering, DTD validation,
and CDATA sections (text is escaped instead). Event attributes such as
`onclick` are accepted as plain keywords rather than dedicated parameters.

## Layout

```
svgwriter/
  elements/      structure/, shapes, text, fonts, paint, clip, filters/, animation
  attributes/    names, length, viewbox, style, reference, descriptors, values
  path/          commands, parser, data, arc, builder
  transform/     matrix, ops, transform
  color/         color keywords, parsing, paint
  io/            writer, parser, async helpers
  builder/       functional API, registered shapes, effects
  document.py    Document with nested-group context managers
  __main__.py    command line
```

## Tests and examples

```
python -m pytest -q
python examples/basic_shapes.py /tmp/out
```
