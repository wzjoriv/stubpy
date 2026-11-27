# stubpy

Generate accurate `.pyi` stubs for your Python package, with `**kwargs` and `*args` traced back to the parameters they forward to. Standard library only.

[![Tests](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml/badge.svg)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![Docs](https://github.com/wzjoriv/stubpy/actions/workflows/docs.yml/badge.svg)](https://github.com/wzjoriv/stubpy/actions/workflows/docs.yml)
[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![CPython 3.10-3.15](https://img.shields.io/badge/CPython-3.10%E2%80%933.15-blue)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![PyPy](https://img.shields.io/badge/PyPy-3.11-blue)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![GraalPy](https://img.shields.io/badge/GraalPy-25-blue)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![Free-threaded](https://img.shields.io/badge/free--threaded-3.14t-blue)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![Pyodide](https://img.shields.io/badge/pyodide-supported-blue)](https://github.com/wzjoriv/stubpy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-wzjoriv.github.io%2Fstubpy-blue)](https://wzjoriv.github.io/stubpy)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Features

| Feature | What you get |
|---|---|
| `**kwargs` / `*args` back-tracing | Forwarded parameters written into the stub signature. |
| Source and runtime | Parses the source and imports the module, merged per symbol; an import policy (`--imports none`) executes nothing. |
| Alias preservation | Aliases like `Length` stay as written, with imports added. |
| Special classes | Dedicated stubs for dataclasses, enums, TypedDict, NamedTuple, Generic, overloads. |
| Compiled extensions | C API, Cython, pybind11 and nanobind modules, including docstrings. |
| Package generation | One command stubs a whole tree, with `__init__.pyi`. |
| Check mode | `stubpy check` exits `1` on missing or stale stubs. |
| Orphan pruning | `--prune` removes stubs whose module no longer exists; stubs tracked in git are kept. |
| Hints | `@hint.signature`, `@hint.returns`, `@hint.ignore` for what introspection misses. |
| Incremental merge | Rewrites only the marked region and keeps hand edits. |
| Stub-only packages | `--stub-package` writes a PEP 561 `<pkg>-stubs` distribution, ready to build. |
| Run cache | `--cache` reuses the stubs of modules unchanged since the last run. |
| Type-checked stubs | `--typecheck` runs mypy (or pyright) over the stubs; errors are reported per stub. |
| Docstring types | `--infer-types` fills missing types from NumPy, Google and Sphinx docstrings. |
| Extension points | Annotation handlers, forwarding resolvers and stub hooks. |
| Configuration | `[tool.stubpy]` in `pyproject.toml`; flags override it. |
| Version branches | `sys.version_info` / `sys.platform` blocks kept, as typeshed does. |
| Lazy attributes | Names behind a module `__getattr__` become explicit. |
| Pre-commit hooks | `stubpy-check` and `stubpy-generate`, ready to use. |

CPython 3.10 to 3.15 (free-threaded 3.14t included), PyPy, GraalPy and Pyodide. No dependencies.

## Install

```bash
pip install stubpy
```

## Use

```bash
stubpy src/mypkg -o stubs        # write stubs/mypkg/**/*.pyi
stubpy check --diff              # exit 1 when a stub is stale
stubpy render mypkg/core.py      # print one stub
```

```python
import stubpy

report = stubpy.generate("src/mypkg", "stubs")   # write stubs
print(stubpy.render("mypkg/core.py").text)       # one module, nothing written
stubpy.check("src/mypkg", "stubs").ok            # False when a stub is stale
```

## Example

```python
# shapes.py
class Shape:
    def __init__(self, color: str = "black", opacity: float = 1.0): ...


class Rect(Shape):
    def __init__(self, width: float, height: float, **kwargs):
        super().__init__(**kwargs)
```

`stubpy render shapes.py`:

```python
class Shape:
    def __init__(self, color: str = 'black', opacity: float = 1.0) -> None: ...

class Rect(Shape):
    def __init__(
        self,
        width: float,
        height: float,
        *,
        color: str = 'black',
        opacity: float = 1.0,
    ) -> None: ...
```

## Configuration

```toml
# pyproject.toml
[tool.stubpy]
targets    = ["src/mypkg"]
output_dir = "stubs"
```

With this, `stubpy` and `stubpy check` need no arguments.

## CI and pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/wzjoriv/stubpy
    rev: 1.0.4
    hooks:
      - id: stubpy-check
```

```yaml
# GitHub Actions step
- run: stubpy check --diff --typecheck
```

## Documentation

- [Quickstart](https://wzjoriv.github.io/stubpy/start/quickstart.html)
- [Examples](https://wzjoriv.github.io/stubpy/start/examples.html): a numbered learning path of scripts and notebooks in [`examples/`](examples/)
- [Command line](https://wzjoriv.github.io/stubpy/guides/cli.html) and [configuration](https://wzjoriv.github.io/stubpy/guides/configuration.html)
- [`*args` / `**kwargs` back-tracing](https://wzjoriv.github.io/stubpy/guides/forwarding.html)
- [CI and pre-commit](https://wzjoriv.github.io/stubpy/guides/ci.html)
- [API reference](https://wzjoriv.github.io/stubpy/reference/api/index.html)
- [Comparison with other tools](https://wzjoriv.github.io/stubpy/explanation/comparison.html)

## Contributing

Setup, the `scripts/dev.py` commands and the project's conventions are in the
[contributing guide](https://wzjoriv.github.io/stubpy/contributing.html).

## License

MIT. See [LICENSE](LICENSE).
