# stubpy

Generate `.pyi` stub files for Python modules with full `**kwargs` / `*args` MRO backtracing, type-alias preservation, Generic support, overload stubs, package batch generation, and cross-file import resolution.

[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Features

- **`**kwargs` backtracing** — walks the entire MRO to expand `**kwargs` into concrete, named parameters at every inheritance level.
- **`cls()` detection** — `@classmethod` methods that forward `**kwargs` into `cls(...)` are resolved against `cls.__init__`, not MRO siblings.
- **Typed `*args` preserved** — explicitly annotated `*args` (e.g. `*elements: Element`) always survive the resolution chain.
- **Positional-only `/` separator** — `def f(a, b, /, c)` stubs correctly emit the PEP 570 `/` separator. Parent positional-only params absorbed by `**kwargs` are promoted to `POSITIONAL_OR_KEYWORD` to keep the child stub valid.
- **TypeVar / Generic / overload** — TypeVar, TypeAlias, NewType, ParamSpec, and TypeVarTuple declarations are re-emitted verbatim. `Generic[T]` bases are preserved via `__orig_bases__`. Each `@overload` variant gets its own stub; the concrete implementation is suppressed per PEP 484.
- **Type-alias preservation** — `types.Length` stays `types.Length` rather than expanding to `str | float | int`. Works inside `Optional[...]`, `tuple[...]`, `list[...]`, and mixed unions.
- **Cross-file imports** — base classes and annotation types from other local modules are re-emitted in the `.pyi` header automatically.
- **Package batch generation** — `generate_package()` recursively stubs a whole directory tree, mirrors the structure, and creates `__init__.pyi` markers for every sub-package.
- **Configuration file** — `stubpy.toml` or `[tool.stubpy]` in `pyproject.toml` controls all options; CLI flags override file values.
- **Typing style** — `"modern"` (default, PEP 604 `X | None`) or `"legacy"` (`Optional[X]`) output.
- **Execution modes** — `RUNTIME` (default), `AST_ONLY` (no module execution), `AUTO` (runtime with graceful fallback).
- **Type alias detection** — explicit `Name: TypeAlias = ...`, bare `Name = int | float`, subscripted generics, known type names, and Python 3.12+ `type Name = ...` (PEP 695) are all detected and emitted correctly.
- **# stubpy: ignore** — place this comment at the top of any source file to exclude it from stub generation entirely.
- **Structured diagnostics** — every pipeline stage records `INFO`, `WARNING`, and `ERROR` entries rather than swallowing exceptions silently.
- **TypedDict / Enum / dataclass stubs** — each class form gets a clean, correct stub without leaking internal implementation details.
- **Enum defaults rendered correctly** — ``ClassName.MEMBER`` form, not the unreadable ``repr()``.
- **NamedTuple extra methods** — ``@property`` and ordinary methods on NamedTuple subclasses are preserved.
- **Glob expansion** — ``stubpy "src/*.py"`` works even without shell expansion.
- **``--include-docstrings``** — embed docstrings in stub bodies.
- **``--infer-types``** — infer parameter/return types from NumPy, Google, or Sphinx docstrings; emitted as `# type:` comments to distinguish from real annotations.
- **``--incremental``** — wrap generated stubs in `# stubpy: auto-generated begin/end` markers; on subsequent runs only the marked region is replaced, preserving manual edits outside the markers.
- **Custom annotation handlers** — ``register_annotation_handler()`` lets you extend the dispatch table.
- **Zero runtime dependencies** — stdlib only.

---

## Installation

```bash
pip install stubpy
# or
uv add stubpy
```

Requires **Python 3.10+**.

---

## Quickstart

### Single file

```bash
stubpy path/to/module.py              # writes module.pyi alongside source
stubpy path/to/module.py -o stubs/   # custom output path
stubpy path/to/module.py --print     # also print to stdout
```

### Multiple files

```bash
stubpy a.py b.py c.py                # stubs written alongside each source
stubpy src/*.py                      # shell glob expansion
stubpy module.py mypackage/          # mix files and directories
```

### Whole package

```bash
stubpy mypackage/                     # stubs written alongside source files
stubpy mypackage/ -o stubs/           # stubs written to stubs/
stubpy mypackage/ --union-style legacy  # use Optional[X] instead of X | None
```

### Configuration file

Place a `stubpy.toml` in the project root (or add `[tool.stubpy]` to `pyproject.toml`):

```toml
# stubpy.toml  (or [tool.stubpy] in pyproject.toml)
include_private   = false
include_docstrings = false          # embed docstrings in stub bodies
union_style       = "modern"        # "modern" (X | None) | "legacy" (Optional[X])
alias_style       = "compatible"    # "compatible" | "pep695" | "auto"
execution_mode    = "runtime"       # "runtime" | "ast_only" | "auto"
output_dir        = "stubs"
exclude           = ["**/test_*.py", "docs/conf.py"]
infer_types       = false           # infer types from docstrings (# type: comments)
incremental       = false           # merge into existing .pyi via markers
```

All flags have CLI equivalents; CLI flags override file values.

---

## How it works

```
generate_stub(filepath)
    │
    ├─ 1. loader      load_module()                → module, path, name
    │        └─ (skipped in AST_ONLY; warning+fallback in AUTO)
    ├─ 2. ast_pass    ast_harvest()                → ASTSymbols
    ├─ 3. imports     scan_import_statements()     → import_map
    ├─ 4. aliases     build_alias_registry()       → ctx populated
    ├─ 5. symbols     build_symbol_table()         → SymbolTable
    ├─ 6. emitter     for each symbol (source order):
    │       ├─ AliasSymbol    → generate_alias_stub()
    │       ├─ ClassSymbol    → generate_class_stub()
    │       │       └─ for each method:
    │       │           resolver  resolve_params()       ← MRO backtracing
    │       │           emitter   generate_method_stub() ← raw AST annotations
    │       ├─ OverloadGroup → generate_overload_group_stub()
    │       ├─ FunctionSymbol → generate_function_stub()
    │       └─ VariableSymbol → generate_variable_stub()
    ├─ 7. imports     collect_typing_imports()     → header
    │                 collect_special_imports()
    │                 collect_cross_imports()
    └─ 8. write       .pyi written to disk

generate_package(package_dir, output_dir)
    └─ for each .py file: generate_stub(...)
    └─ ensure __init__.pyi for each sub-package
```

`resolve_params` uses three strategies in order:

1. **No variadics** — return own parameters unchanged.
2. **`cls()` detection** — AST-detect `cls(..., **kwargs)` in classmethods; resolve against `cls.__init__`.
3. **MRO walk** — collect concrete parameters from each ancestor until all variadics are resolved. `POSITIONAL_ONLY` params absorbed by `**kwargs` are promoted to `POSITIONAL_OR_KEYWORD`.

---

## CLI reference

```
usage: stubpy [-h] [-o PATH] [--print] [--include-private] [--include-docstrings]
              [--verbose] [--strict] [--infer-types] [--incremental]
              [--union-style {modern,legacy}] [--alias-style {compatible,pep695,auto}]
              [--execution-mode {runtime,ast_only,auto}]
              [--exclude PATTERN] [--no-respect-all] [--no-config]
              path [path ...]

positional arguments:
  path                    .py file(s), package directories, or glob patterns

optional arguments:
  -o PATH                 Output .pyi path (file) or root directory (package)
  --print                 Print generated stub to stdout (file mode only)
  --include-private       Include symbols whose names start with _
  --include-docstrings    Embed docstrings as triple-quoted stub bodies
  --verbose               Print INFO / WARNING / ERROR diagnostics to stderr
  --strict                Exit 1 if any ERROR diagnostic was recorded
  --infer-types           Infer types from NumPy/Google/Sphinx docstrings;
                          emitted as # type: comments (not live annotations)
  --incremental           Wrap stub in auto-generated markers and merge into
                          existing .pyi, preserving manual edits outside markers
  --union-style STYLE     modern (X | None, default) | legacy (Optional[X])
  --alias-style STYLE     compatible (default) | pep695 | auto
  --execution-mode MODE   runtime (default) | ast_only | auto
  --exclude PATTERN       Skip files matching this glob pattern (repeatable)
  --no-respect-all        Stub all symbols even when __all__ is defined
  --no-config             Ignore stubpy.toml / pyproject.toml
```

---

## Python API

```python
from stubpy import generate_stub, generate_package, load_config, StubContext, StubConfig

# Single file
content = generate_stub("mymodule.py")
content = generate_stub("mymodule.py", "stubs/mymodule.pyi")

# Whole package
result = generate_package("mypackage/", "stubs/")
print(result.summary())   # "Generated 12 stubs, 0 failed."

# Custom config
cfg = StubConfig(union_style="legacy", exclude=["**/migrations/*.py"])
result = generate_package("myapp/", "stubs/", config=cfg)

# Per-file context factory — receives (source_path, output_path)
from pathlib import Path
def my_factory(src: Path, out: Path):
    mode = "ast_only" if "generated" in src.name else "runtime"
    return StubContext(config=StubConfig(execution_mode=mode))
result = generate_package("myapp/", "stubs/", ctx_factory=my_factory)

# Load config from file (stubpy.toml or pyproject.toml)
cfg = load_config(".")
result = generate_package("mypackage/", config=cfg)
```

### Extended public API

```python
# Context and configuration
from stubpy import StubContext, StubConfig, ExecutionMode, AliasEntry

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

# Emitters (public for extension)
from stubpy import (
    generate_class_stub, generate_function_stub, generate_variable_stub,
    generate_alias_stub, generate_overload_group_stub,
)

# Config file support
from stubpy import find_config_file, load_config
```

---

## Example

```python
# shapes.py
from typing import TypeVar, Generic, overload

T = TypeVar("T")

class Shape:
    def __init__(self, color: str = "black", opacity: float = 1.0) -> None: ...

class Circle(Shape):
    def __init__(self, radius: float, **kwargs) -> None:
        super().__init__(**kwargs)

    @classmethod
    def unit(cls, **kwargs) -> "Circle":
        return cls(radius=1.0, **kwargs)

class Box(Generic[T]):
    def put(self, item: T) -> None: ...
    def get(self) -> T: ...

@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x): return x
```

```bash
stubpy shapes.py --print
```

```python
# shapes.pyi  (generated)
from __future__ import annotations
from typing import Generic, TypeVar, overload

T = TypeVar('T')

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

class Box(Generic[T]):
    def put(self, item: T) -> None: ...
    def get(self) -> T: ...

@overload
def parse(x: int) -> int: ...

@overload
def parse(x: str) -> str: ...
```

---

## Project layout

```
stubpy/
├── stubpy/                 ← package (stdlib only, no runtime deps)
│   ├── context.py          StubContext, StubConfig, ExecutionMode
│   ├── diagnostics.py      DiagnosticCollector, Diagnostic
│   ├── ast_pass.py         ast_harvest, ASTSymbols
│   ├── symbols.py          SymbolTable, StubSymbol hierarchy
│   ├── loader.py           load_module
│   ├── aliases.py          build_alias_registry
│   ├── imports.py          scan / collect imports
│   ├── annotations.py      dispatch-table annotation_to_str
│   ├── resolver.py         resolve_params (MRO backtracing + pos-only normalisation)
│   ├── emitter.py          generate_class / method / function / alias / overload stubs
│   ├── generator.py        generate_stub + generate_package orchestrator
│   ├── config.py           find_config_file, load_config (TOML parsing)
│   └── __main__.py         CLI entry point
├── demo/                   demo package used for integration tests
├── tests/                  pytest suite (730+ tests)
│   ├── test_annotations.py
│   ├── test_ast_pass.py
│   ├── test_config.py
│   ├── test_context.py
│   ├── test_diagnostics.py
│   ├── test_emitter.py
│   ├── test_imports.py
│   ├── test_integration.py
│   ├── test_loader.py
│   ├── test_module_symbols.py
│   ├── test_resolver.py
│   ├── test_special_classes.py
│   └── test_symbols.py
├── docs/                   Sphinx + Furo documentation
├── LICENSE
└── pyproject.toml
```

---

## Development setup

```bash
git clone https://github.com/wzjoriv/stubpy.git
cd stubpy
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Build the docs:

```bash
pip install -e ".[docs]"
cd docs && make html
# open docs/_build/html/index.html
```

---

## Documentation

Full documentation including **per-symbol API pages**, example walkthroughs,
and the "How it works" guide is available at:
[https://wzjoriv.github.io/stubpy](https://wzjoriv.github.io/stubpy)

Every public function and class has its own page with:
- Full parameter descriptions (from docstrings)
- Usage examples
- Source link

## License

[MIT](LICENSE) © 2026 [Josue N Rivera](https://github.com/wzjoriv)
