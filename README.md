# stubpy

Generate `.pyi` stub files for Python modules with full `**kwargs` / `*args` MRO backtracing, type-alias preservation, and cross-file import resolution.

[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- **`**kwargs` backtracing** — walks the entire MRO to expand `**kwargs` into concrete, named parameters at every inheritance level.
- **`cls()` detection** — `@classmethod` methods that forward `**kwargs` into `cls(...)` are resolved against `cls.__init__`, not MRO siblings.
- **Typed `*args` preserved** — explicitly annotated `*args` (e.g. `*elements: Element`) always survive the resolution chain.
- **Type-alias preservation** — `types.Length` stays `types.Length` rather than expanding to `str | float | int`. Aliases inside `Optional[...]`, `tuple[...]`, `list[...]`, and `Union[..., None]` are also preserved.
- **Cross-file imports** — base classes and annotation types from other local modules are re-emitted in the `.pyi` header automatically.
- **AST pre-pass** — a read-only AST harvest runs before module execution, recovering alias names that Python's `typing.Union` would otherwise flatten at runtime.
- **Structured diagnostics** — every pipeline stage records `INFO`, `WARNING`, and `ERROR` entries in a `DiagnosticCollector` rather than swallowing exceptions silently.
- **Unified symbol table** — classes, functions, variables, type aliases, and overload groups are all represented as typed `StubSymbol` entries in a `SymbolTable`.
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

---

## How it works

stubpy runs a nine-stage pipeline, each stage in its own module:

```
generate_stub(filepath)
    │
    ├─ 1. loader      load_module()              load source as a live module
    ├─ 2. ast_pass    ast_harvest()              read-only AST pre-pass
    ├─ 3. imports     scan_import_statements()   parse AST → {name: import_stmt}
    ├─ 4. aliases     build_alias_registry()     discover type-alias sub-modules
    ├─ 5. symbols     build_symbol_table()       merge AST + runtime → SymbolTable
    ├─ 6. generator   collect_classes()          gather classes in source order
    │       └─ for each class:
    │           emitter   generate_class_stub()
    │               └─ for each method:
    │                   resolver  resolve_params()      ← MRO backtracing
    │                   emitter   generate_method_stub()  ← AST raw annotations
    └─ 7. generator   assemble header + body     → write .pyi
```

**`resolve_params` uses three strategies in order:**

1. **No variadics** — if the method has neither `*args` nor `**kwargs`, return its own parameters unchanged.
2. **`cls()` detection** — if a `@classmethod` body contains `cls(..., **kwargs)`, the `**kwargs` is resolved against `cls.__init__` via AST analysis. Parameters hardcoded in the call are excluded.
3. **MRO walk** — walk ancestor classes that define the same method, collecting concrete parameters until all variadics are fully resolved.

**`StubContext`** carries all mutable state for one run. A fresh instance is created per `generate_stub()` call, making the generator fully re-entrant.

---

## CLI

```bash
stubpy path/to/module.py                    # writes module.pyi alongside source
stubpy path/to/module.py -o out/module.pyi  # custom output path
stubpy path/to/module.py --print            # also print to stdout
stubpy path/to/module.py --verbose          # print all diagnostics to stderr
stubpy path/to/module.py --strict           # exit 1 if any ERROR diagnostic
```

## Python API

```python
from stubpy import generate_stub

content = generate_stub("path/to/module.py")
content = generate_stub("path/to/module.py", "out/module.pyi")
```

### Extended public API

```python
# Diagnostics
from stubpy import DiagnosticCollector, DiagnosticLevel, DiagnosticStage, Diagnostic

# AST pre-pass
from stubpy import ast_harvest, ASTSymbols

# Symbol table
from stubpy import (
    SymbolTable, SymbolKind,
    ClassSymbol, FunctionSymbol, VariableSymbol, AliasSymbol, OverloadGroup,
    build_symbol_table,
)

# Configuration
from stubpy import StubContext, StubConfig, ExecutionMode
```

---

## Documentation (optional)

```bash
# Install documentation dependencies
pip install -e ".[docs]"

# Build the HTML site
cd docs && make html
# → open docs/_build/html/index.html in a browser
```

---

## Installation (end users)

```bash
pip install stubpy
# or
uv add stubpy
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

---

## Project layout

```
stubpy/
├── stubpy/             ← package (stdlib only, no runtime deps)
│   ├── context.py      StubContext, AliasEntry, StubConfig, ExecutionMode
│   ├── diagnostics.py  DiagnosticCollector, Diagnostic
│   ├── ast_pass.py     ast_harvest, ASTSymbols
│   ├── symbols.py      SymbolTable, StubSymbol hierarchy
│   ├── loader.py       load_module
│   ├── aliases.py      build_alias_registry
│   ├── imports.py      scan / collect imports
│   ├── annotations.py  dispatch-table annotation_to_str
│   ├── resolver.py     resolve_params (3 strategies)
│   ├── emitter.py      generate_class / method stub
│   └── generator.py    generate_stub orchestrator
├── demo/               demo package used for integration tests
├── tests/              pytest suite (435+ tests)
├── docs/               Sphinx + Furo documentation
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

[MIT](LICENSE) © 2026 [Josue N Rivera](https://github.com/wzjoriv)
