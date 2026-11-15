# svgwriter roadmap

A critical look at svgwriter 1.0 from the point of view of someone using it
to draw things, the plan that came out of it, what 1.1 delivered and what
is left.

## Review of 1.0

### API ergonomics

- Every element is built twice: `doc.add(svg.Circle(50, 50, 10))`. The
  document knows where things go but offers no `doc.circle(...)`.
- Definitions need two steps and a variable: `grad = doc.define(...)` then
  `fill=grad`. There is no short way to say "put this in `<defs>` and give
  me its reference".
- `Document.group` is only a context manager. Getting a group back to fill
  later, or nesting without `with`, means building a `Group` by hand.
- `Transform.rotate(30)` looks right but fails: the builders are instance
  methods, so it has to be `Transform().rotate(30)`. `Matrix @ Transform`
  raises `AttributeError` instead of composing.
- Path data cannot be transformed or combined at the element level.
  `PathData + PathData` exists, `Path + Path` does not, and a transform can
  only be attached, never baked into the coordinates.
- `Color.mix` and `lighten` exist but colors do not compose with operators.
- `add_shape("circle", r=3)` is a stringly-typed duplicate of the classes.

### Discoverability and naming

- Two parallel lowercase vocabularies: `svgwriter.builder.polyline(*points)`
  takes points as varargs, `Polyline(points)` takes a sequence, and only the
  classes are exported at the top level.
- `Svg.defs()` is a method, `Document.defs` a property.
- Geometry questions ("how long is this path", "is this point inside") have
  no home; `bbox` silently samples curves.

### Missing conveniences

- No shape-to-path conversion, no boolean operations, no text outlines.
- No way to preview or export the SMIL/procedural animation the element
  classes can describe.
- No `_repr_svg_`, so documents do not display in notebooks.
- No `py.typed` marker even though the classifier claims `Typing :: Typed`.

### SVG 1.1 coverage

- `script`, `foreignObject`, `cursor` and the `on*` event attributes are
  browser-scripting features. They have nothing to do with drawing, nothing
  in the library renders or measures them, and event attributes slip in
  through `**kwargs` unchecked. They should go.
- `a`, `view` and `switch` are legitimate static SVG and stay.
- Everything else in SVG 1.1 has a class; the gaps are behavioural (no
  geometry engine, no font metrics), not structural.

### Errors, docs and examples

- Typos in keyword names (`strok="red"`) are written to the output silently.
  Worth a "did you mean" check for known attribute names (see Later).
- `parse_transform` reports arity as a tuple: `takes (1, 3) arguments`.
- The README teaches the verbose `doc.add(svg.X(...))` style; examples never
  show reuse via `<defs>` beyond a single gradient.

### Performance

Building 20 000 circles takes about 0.23 s, writing 0.17 s, parsing 0.15 s
(1.2 MB). That is fine. `Element.iter` builds a list per node and
`get_element_by_id` is a linear walk; both are acceptable at this size.

### Packaging

- No extras; the version is still 1.0.0; no `py.typed`; no Python version
  classifiers.

## Plan, in priority order

1. Lowercase aliases for every element class (`path`, `circle`,
   `linear_gradient`, ...) exported from the package.
2. Document and container shortcuts (`doc.circle(...)`,
   `doc.linear_gradient(...)` into `<defs>`, ...) that forward `**kwargs` to
   the element constructor and return the element. Container shortcuts work
   as context managers.
3. Composition operators: `+=` / `+` for containers and groups, `%` / `%=`
   for definitions, `+` / `*` / `@` for path data, `|` `&` `-` `^` boolean
   operations, `@` for transforms, `+` / `*` for colors.
4. Optional skia-python geometry (`svgwriter[ops]`): boolean operations,
   `text_to_path`, simplify, stroke-to-path, exact bounds, hit testing,
   length and point-at-length.
5. Remove `script`, `foreignObject`, `cursor` and event attributes.
6. `Document.render_animation` through a pluggable renderer and `ffmpeg`,
   plus `python -m svgwriter animate`.
7. Modern typing spellings (`X | Y` aliases, `collections.abc`,
   `contextlib.AbstractContextManager`).
8. `py.typed`, extras, version 1.1.0, notebook display, clearer errors.

## Done in 1.1

1. **Lowercase aliases** for all 77 element classes (`svg.circle`,
   `svg.linear_gradient`, `svg.fe_gaussian_blur`, ...) in
   `svgwriter.aliases`, re-exported from the package. `filter` and `set`
   are package attributes but stay out of `__all__` so a star import does
   not shadow the builtins.
2. **Shortcuts** on `Document` and every drawing container through
   `ElementFactory`: `rect`, `circle`, `ellipse`, `line`, `polyline`,
   `polygon`, `path`, `text`, `group`, `link`, `switch`, `use`, `image`, and
   into `<defs>`: `linear_gradient`, `radial_gradient`, `pattern`,
   `clip_path`, `mask`, `marker`, `filter`, `symbol`. Each forwards
   `*args, **kwargs` to the element constructor. Returned containers nest
   with `with`, including definitions (`with doc.clip_path(): ...`).
   `doc.group()` keeps working as before inside `with`.
3. **Operators**: `+=` / `+` on containers and elements, `%` / `%=` for
   definitions, `Path + Path`, `PathData + PathData`, `sum()` over path
   data, `*` / `@` baking transforms into any shape (exact for arcs), the
   four boolean operators with reflected and in-place forms,
   `Transform.rotate(30) @ Transform.scale(2)` (builders work on the class),
   `Matrix @ Transform`, `t @ (x, y)`, `Color + Color`, `color * 0.5`,
   `0.5 * color`, `color / 2`. `@overload` types the operators that accept
   several kinds.
4. **skia-python geometry** in `svgwriter.ops` and on every shape and
   `<text>`: boolean operations, `text_to_path`, `text_width`, simplify,
   stroke-to-path, exact bounds, `contains_point`, `total_length`,
   `point_at_length`, tangent, and `rasterize` to PNG. Optional extra
   `svgwriter[ops]`; without it everything imports and these raise
   `MissingDependencyError` naming the install command.
5. **Web-only content removed**: `script`, `foreignObject`, `cursor`, the
   `cursor` property, `contentScriptType` and every `on*` event attribute.
   Setting them raises `ValueError`; the parser drops them (strict mode
   raises).
6. **Animation export**: `Document.render_animation()` and
   `svgwriter.video` render frames through any renderer returning PNG bytes
   or RGBA arrays and pipe them to ffmpeg (mp4, gif, webm, mov, apng).
   Renderers are callables, registered names (`"skia"` built in) or
   `"module:function"`. Missing ffmpeg raises `FFmpegNotFoundError` before
   any rendering. Duration defaults to the end of the SMIL animations.
   CLI: `animate`, plus `render` (PNG) and `outline` (text to paths).
7. **Typing**: `X | Y` aliases with `TypeAlias`, `collections.abc`
   everywhere, containers are `contextlib.AbstractContextManager`s.
8. Also: `Shape.to_path()` for every shape (pure Python, honours `rx`/`ry`
   rules and `transform`), `PathData.transformed()` and `subpaths()`,
   `Transform.inverse()`, `_repr_svg_` for notebooks, `Document.style()`,
   `href=doc % symbol` writes `#id`, clearer errors (transform arity, color
   channel, point counts), `Element.iter` without per-node lists, `py.typed`,
   version 1.1.0, extras and classifiers, `shapes` split into a
   sub-package and the CLI into `svgwriter.cli`.

## Later

- **Attribute name checking.** Warn on unknown keyword names with a "did you
  mean" (`strok_width`); needs a per-element table of valid attributes.
- **Geometry-first attribute order.** Presentation keywords are written
  before the geometry (`<circle fill="red" cx=...>`); swapping is a visible
  output change, so it waits for 2.0.
- **`svgwriter.path` name clash.** The `path` alias replaces the
  sub-package as an attribute of `svgwriter`, so `import svgwriter.path as
  p` now yields the class; `from svgwriter.path import ...` is unaffected.
  Renaming the sub-package (`svgwriter.pathdata`) would remove the clash.
- **The `builder` module** predates the aliases and its lowercase functions
  differ in signature (`builder.polyline(*points)` vs `svg.polyline(points)`).
  Deprecate the duplicates and keep the composite shapes and effects.
- **SMIL evaluation.** A renderer receives the document and the time; a
  helper that applies SMIL values at time *t* would let static renderers
  play `<animate>` without an `update` callback.
- **Text layout without skia**: font metrics for `text_width` from an AFM
  table of the core fonts.
- **Id index.** `get_element_by_id` walks the tree; an index kept by
  `Element.id` would make large documents faster.
- **Pure-Python fallbacks** for `total_length` and `point_at_length` using
  the existing curve sampling.
