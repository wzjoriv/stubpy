# drawlib (stubpy corpus)

A deliberately small slice of an SVG writer, kept only as real-world input for
stubpy's tests (`tests/integration/test_drawlib_corpus.py`) and
`python scripts/dev.py stubpy corpus`. The real library is the separate
`drawlib` project; this copy is not meant to be installed or used.

It keeps the constructs stubpy has to handle: deep cooperative `**kwargs`
mixin chains, `cls()` factories, shortcut methods with function-local imports,
operators with `@overload` and their reflected / in-place forms, lowercase
class aliases, Generic / ParamSpec / Concatenate, Protocol and ABC, dataclasses
(`InitVar`, `kw_only`), NamedTuple, TypedDict, enum flavours, descriptors,
`__init_subclass__` keywords, `functools.partial` / `lru_cache` /
`singledispatch`, module `__getattr__`, `TYPE_CHECKING` and
`sys.version_info` branches, a version-guarded PEP 695 module, an optional
skia import, async helpers, registry dispatch, `open()` and template
forwarding, `#` inside string defaults, and hidden or non-identifier files that
default excludes skip.
