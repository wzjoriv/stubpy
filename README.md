# stubpy

Generate `.pyi` stub files for Python modules with full `**kwargs` / `*args` MRO backtracing, type-alias preservation, and cross-file import resolution.

[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- **`**kwargs` backtracing** — walks the entire MRO to expand `**kwargs` into concrete, named parameters at every inheritance level.
- **`cls()` detection** — `@classmethod` methods that forward `**kwargs` into `cls(...)` are resolved against `cls.__init__`, not MRO siblings.
- **Typed `*args` preserved** — explicitly annotated `*args` (e.g. `*elements: Element`) always survive the resolution chain.
- **Type-alias preservation** — `types.Length` stays `types.Length` rather than expanding to `str | float | int`.
- **Cross-file imports** — base classes and annotation types from other local modules are re-emitted in the `.pyi` header automatically.
- **Zero runtime dependencies** — stdlib only.

---

## Environment setup

> Requires **Python 3.10+**. The steps below use the Windows Python Launcher (`py`).  
> On macOS / Linux replace `py -3.10` with `python3.10`.

```bash
# 1. Clone the repository
git clone https://github.com/wzjoriv/stubpy.git
cd stubpy

# 2. Create a virtual environment with Python 3.11
py -3.11 -m venv .venv

# 3. Activate the environment
.venv\Scripts\activate          # Windows CMD / PowerShell
# source .venv/bin/activate     # macOS / Linux

# 4. Install in editable mode with development dependencies
pip install -e ".[dev]"

# 5. Verify — run the full test suite
pytest
```

#
## How it works

stubpy is a pipeline of six focused stages, each in its own module:

```
generate_stub(filepath)
    │
    ├─ 1. loader      load_module()             load source as a live module
    ├─ 2. imports     scan_import_statements()  parse AST → {name: import_stmt}
    ├─ 3. aliases     build_alias_registry()    discover type-alias sub-modules
    ├─ 4. generator   collect_classes()         gather classes in source order
    │       └─ for each class:
    │           emitter   generate_class_stub()
    │               └─ for each method:
    │                   resolver  resolve_params()     ← MRO backtracing
    │                   emitter   generate_method_stub()
    └─ 5. generator   assemble header + body    → write .pyi
```

**`resolve_params` uses three strategies in order:**

1. **No variadics** — if the method has neither `*args` nor `**kwargs`, return its own parameters unchanged.
2. **`cls()` detection** — if a `@classmethod` body contains `cls(..., **kwargs)`, the `**kwargs` is resolved against `cls.__init__` via AST analysis. Parameters hardcoded in the call are excluded.
3. **MRO walk** — walk ancestor classes that define the same method, collecting concrete parameters until all variadics are fully resolved.

**`StubContext`** carries all mutable state for one run (alias registry, used imports). A fresh instance is created per `generate_stub()` call, making the generator fully re-entrant.

---

## Installation (end users)

```bash
pip install stubpy
# or
uv add stubpy
```

---

## Usage

### CLI

```bash
stubpy path/to/module.py                    # writes module.pyi alongside source
stubpy path/to/module.py -o out/module.pyi  # custom output path
stubpy path/to/module.py --print            # also print to stdout
```

### Python API

```python
from stubpy import generate_stub

content = generate_stub("path/to/module.py")
content = generate_stub("path/to/module.py", "out/module.pyi")
```

---

## Example

```python
# shapes.py
class Shape:
    def __init__(self, color: str = "black", opacity: float = 1.0) -> None: ...

class Circle(Shape):
    def __init__(self, radius: float, **kwargs) -> None:
        super().__init__(**kwargs)

    @classmethod
    def unit(cls, **kwargs) -> "Circle":
        return cls(radius=1.0, **kwargs)
```

```bash
stubpy shapes.py --print
```

```python
# shapes.pyi  (generated)
from __future__ import annotations

class Shape:
    def __init__(self, color: str = 'black', opacity: float = 1.0) -> None: ...

class Circle(Shape):
    def __init__(
        self,
        radius: float,
        color: str = 'black',
        opacity: float = 1.0,
    ) -> None: ...
    @classmethod
    def unit(cls, color: str = 'black', opacity: float = 1.0) -> Circle: ...
```

`**kwargs` in `Circle.__init__` resolves to `color` and `opacity` from `Shape.__init__`. `Circle.unit` detects `cls(radius=1.0, **kwargs)` via AST — `radius` is hardcoded so it's excluded; the remaining `Shape` params appear.

---
## Documentation

Full documentation at **[wzjoriv.github.io/stubpy](https://wzjoriv.github.io/stubpy)** including:

- [Getting Started](https://wzjoriv.github.io/stubpy/guides/quickstart.html)
- [How It Works](https://wzjoriv.github.io/stubpy/guides/how_it_works.html)
- [API Reference](https://wzjoriv.github.io/stubpy/api/index.html)

---

## Project layout

```
stubpy/
├── stubpy/            ← package (stdlib only, no runtime deps)
│   ├── context.py     StubContext, AliasEntry
│   ├── loader.py      load_module
│   ├── aliases.py     build_alias_registry
│   ├── imports.py     scan / collect imports
│   ├── annotations.py dispatch-table annotation_to_str
│   ├── resolver.py    resolve_params (3 strategies)
│   ├── emitter.py     generate_class / method stub
│   └── generator.py   generate_stub orchestrator
├── demo/              demo package used for integration tests
├── tests/             pytest suite (~235 tests)
├── docs/              Sphinx + Furo documentation
├── LICENSE
└── pyproject.toml
```

---

## Contributing

```bash
git clone https://github.com/wzjoriv/stubpy.git
cd stubpy
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

---

## License

[MIT](LICENSE) © 2024 [Josue N Rivera](https://github.com/wzjoriv)
