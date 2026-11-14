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
- **Package batch generation** — `stubpy.generate()` recursively stubs a whole directory tree, mirrors the structure, and creates `__init__.pyi` markers for every sub-package.
- **Stale-stub checks** — `stubpy check` / `stubpy.check()` compare the stubs on disk with what would be generated; ready for CI and pre-commit.
- **Hints** — `@hint.signature`, `@hint.returns` and `@hint.ignore` cover what introspection cannot see (JIT, C, dynamic code) at zero runtime cost.
- **Configuration file** — `stubpy.toml` or `[tool.stubpy]` in `pyproject.toml` controls all options; CLI flags override file values.
- **Typing style** — `"modern"` (default, PEP 604 `X | None`) or `"legacy"` (`Optional[X]`) output.
- **Execution modes** — `runtime` (default), `ast` (no module execution), `auto` (runtime with graceful fallback).
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
- **Custom annotation handlers** — ``stubpy.extend.register_annotation_handler()`` lets you extend the dispatch table.
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

### Generate

```bash
stubpy path/to/module.py                  # writes module.pyi next to the source
stubpy path/to/module.py -o out/mod.pyi   # an explicit stub file
stubpy src/mypkg -o stubs                 # writes stubs/mypkg/**/*.pyi (a stub root)
stubpy "src/**/*.py"                      # quoted globs work without shell expansion
stubpy mypkg.core -o stubs                # an importable module by dotted name
stubpy                                    # the targets from [tool.stubpy]
```

### Check (CI and pre-commit)

```bash
stubpy check src/mypkg -o stubs           # exit 1 when a stub is missing or differs
stubpy check src/mypkg -o stubs --diff    # and show a unified diff
```

### Render

```bash
stubpy render path/to/module.py           # print the stub; nothing is written
stubpy render mypkg.core --mode ast
```

### Configuration file

Place a `stubpy.toml` in the project root (or add `[tool.stubpy]` to `pyproject.toml`):

```toml
[tool.stubpy]
targets            = ["src/mypkg"]      # what `stubpy` / `stubpy check` act on with no paths
modules            = ["mypkg._native"]  # importable modules, by dotted name
output_dir         = "stubs"            # stub root; omit to write next to the sources
mode               = "runtime"          # "runtime" | "ast" | "auto"
include_private    = false
include_docstrings = false              # embed docstrings in stub bodies
union_style        = "modern"           # "modern" (X | None) | "legacy" (Optional[X])
alias_style        = "compatible"       # "compatible" | "pep695" | "auto"
exclude            = ["**/test_*.py"]   # globs relative to a folder target
infer_types        = false              # infer types from docstrings
incremental        = false              # merge into existing .pyi via markers
resolve_kwargs     = true               # false keeps **kwargs as-is (typeshed style)
resolve_args       = true               # false keeps *args as-is
```

Paths are relative to the file that holds them. Unknown keys are an error. CLI flags override file values.

### pre-commit

```yaml
repos:
  - repo: https://github.com/wzjoriv/stubpy
    rev: v0.7.0
    hooks:
      - id: stubpy-check      # or stubpy-generate
```

Both hooks act on the configured `targets` / `modules`.

---

## How it works

```
stubpy.render(target)
    │
    ├─ 1. loader      load_module()                → module, path, name
    │        └─ (skipped in ast mode; warning+fallback in auto)
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
    └─ 8. result      StubResult(text, diagnostics)

stubpy.generate(target, output) / stubpy.check(target, output)
    └─ for each module: render, merge (incremental), then write or compare
    └─ ensure __init__.pyi for each package in the stub tree
```

`resolve_params` uses three strategies in order:

1. **No variadics** — return own parameters unchanged.
2. **`cls()` detection** — AST-detect `cls(..., **kwargs)` in classmethods; resolve against `cls.__init__`.
3. **MRO walk** — collect concrete parameters from each ancestor until all variadics are resolved. `POSITIONAL_ONLY` params absorbed by `**kwargs` are promoted to `POSITIONAL_OR_KEYWORD`.

---

## CLI reference

```
stubpy [generate] [TARGET ...] [-o OUT] [options]   write stubs (the default command)
stubpy check [TARGET ...] [-o OUT] [--diff] [options]
stubpy render TARGET [options]                      print one stub to stdout
stubpy --version

A TARGET is a .py file, a folder, a quoted glob or a dotted module name.
With no TARGET, the configured 'targets' and 'modules' are used.

  -o, --output OUT        a .pyi file for a single file target, otherwise a stub root folder
  --diff                  (check) print a unified diff for each stale stub
  --mode MODE             runtime (default) | ast | auto
  --include-private       stub names starting with _
  --include-docstrings    use docstrings as stub bodies
  --infer-types           fill missing types from NumPy / Google / Sphinx docstrings
  --incremental           merge into existing stubs, keeping edits outside the markers
  --no-resolve-kwargs     keep **kwargs as written (typeshed convention)
  --no-resolve-args       keep *args as written
  --no-respect-all        stub every public name even when __all__ is defined
  --union-style STYLE     modern (X | None, default) | legacy (Optional[X])
  --alias-style STYLE     compatible (default) | pep695 | auto
  --exclude PATTERN       skip files matching this glob (repeatable)
  --no-config             ignore stubpy.toml / [tool.stubpy]
  --verbose               print every diagnostic
  --strict                count warnings as failures
  -q, --quiet             print errors only

Exit codes: 0 ok; 1 stale stubs or failed modules; 2 usage error, bad config or unknown target.
```

---

## Python API

```python
import stubpy

result = stubpy.render("mymodule.py")            # StubResult; nothing is written
print(result.text, result.ok, result.diagnostics)

report = stubpy.generate("src/mypkg", "stubs")   # Report
print(report.summary())                          # "Generated 12 stubs, 0 failed."
for failed in report.failed:
    print(failed.module_name, failed.errors)

report = stubpy.check("src/mypkg", "stubs")      # nothing is written
if not report.ok:
    print("stale:", report.stale)

cfg = stubpy.Config(mode="ast", union_style="legacy", exclude=["**/migrations/*.py"])
stubpy.generate("myapp", "stubs", config=cfg)
stubpy.generate(config=stubpy.load_config())     # targets and options from [tool.stubpy]
```

Targets are auto-detected: a `.py` file, a folder, a glob, a dotted module name, or a list of them.
`Config` is immutable; `cfg.replace(strict=True)` and `Config.from_dict({...})` build new ones.

### Hints

Zero-cost decorators for what introspection cannot see; they only set an attribute, and stubpy also reads
them from the source in `ast` mode. They never appear in the stub.

```python
from stubpy import hint

@hint.signature("(x: float, y: float) -> float")   # JIT, C or dynamically built callables
@numba.njit
def dist(x, y): ...

@hint.returns("np.ndarray")                        # keep the parameters, fix the return type
def load(path): ...

@hint.ignore                                       # never stubbed
def _debug_dump(): ...
```

### Extending

```python
from stubpy.extend import annotation_to_str, register_annotation_handler

@register_annotation_handler(lambda a: isinstance(a, Validated), first=True)
def _validated(annotation, ctx):
    return f"Validated[{annotation_to_str(annotation.inner_type, ctx)}]"
```

`stubpy.extend` also exposes `StubContext`, the symbol classes (`SymbolTable`, `ClassSymbol`, ...), the
diagnostics classes (`Diagnostic`, `DiagnosticCollector`, `Level`, `Stage`) and `ast_harvest` /
`build_symbol_table`.

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
stubpy render shapes.py
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
├── stubpy/            the package (stdlib only)
│   ├── __init__.py    render, generate, check, Config, Mode, load_config, StubResult, Report, ...
│   ├── hint.py        @hint.signature / @hint.returns / @hint.ignore
│   ├── extend.py      extension points: handlers, StubContext, symbols, diagnostics
│   ├── config/        Config, Mode, style enums, stubpy.toml / [tool.stubpy] loading
│   ├── core/          context, diagnostics, results, targets, pipeline, api
│   ├── analysis/      loader, AST harvest, imports, aliases, hints, symbols, docstrings
│   ├── resolve/       **kwargs / *args back-tracing
│   ├── emit/          stub text for classes, functions, variables, aliases, overloads
│   └── cli/           the stubpy command
├── demo/              demo package used for integration tests
├── tests/             pytest suite, mirroring the package
├── docs/              Sphinx + Furo documentation
├── .pre-commit-hooks.yaml
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
