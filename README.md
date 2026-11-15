# stubpy

Generate accurate `.pyi` stubs for your Python package, with `**kwargs` and `*args` traced back to the parameters they forward to. Standard library only.

[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-wzjoriv.github.io%2Fstubpy-blue)](https://wzjoriv.github.io/stubpy)

## Features

| Feature | What you get |
|---|---|
| `**kwargs` / `*args` back-tracing | Forwarded parameters are written into the stub, through the MRO, `cls(...)`, `self.method(...)` and plain function calls. |
| Runtime, AST or auto | `runtime` imports the module, `ast` only parses it, `auto` falls back to `ast` when the import fails. |
| Alias preservation | Aliases keep their names (`Length`, `types.Length`) instead of expanding to `str \| float \| int`, with the import added. |
| Special classes | Dataclasses, `Enum`, `TypedDict`, `NamedTuple`, `Generic`, `TypeVar` and `@overload` get dedicated stubs. |
| Version branches | `if sys.version_info >= (3, 12):` / `if sys.platform == "win32":` blocks are kept with every branch, as typeshed writes them. |
| Lazy attributes | Names a module `__getattr__` loads lazily are written as re-exports, and `__getattr__` leaves the stub once all are known. |
| Compiled modules | C API, Cython, pybind11 and nanobind extensions: overloads, enums, properties and numpy types, plus `stubpy docstrings sync` for hand-written stubs. |
| Package generation | One command stubs a whole tree, mirrors its layout and adds `__init__.pyi`. |
| Check mode | `stubpy check` exits `1` when a stub is missing or stale; `--diff` shows the change. |
| Hints | `@hint.signature`, `@hint.returns` and `@hint.ignore` cover what introspection cannot see. |
| Incremental merge | `--incremental` replaces only the marked region of a stub and keeps your hand edits. |
| Configuration | `[tool.stubpy]` in `pyproject.toml` or `stubpy.toml`; command-line flags override it. |
| Pre-commit hooks | `stubpy-check` and `stubpy-generate` run on the configured targets. |
| Extension points | Register annotation handlers and read the symbol table through `stubpy.extend`. |

Python 3.10 to 3.15 and PyPy. No dependencies.

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
mode       = "auto"
```

With this, `stubpy` and `stubpy check` need no arguments.

## CI and pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/wzjoriv/stubpy
    rev: v0.7.0
    hooks:
      - id: stubpy-check
```

```yaml
# GitHub Actions step
- run: stubpy check --diff
```

## Documentation

- [Quickstart](https://wzjoriv.github.io/stubpy/start/quickstart.html)
- [Command line](https://wzjoriv.github.io/stubpy/guides/cli.html) and [configuration](https://wzjoriv.github.io/stubpy/guides/configuration.html)
- [`**kwargs` back-tracing](https://wzjoriv.github.io/stubpy/guides/kwargs.html)
- [CI and pre-commit](https://wzjoriv.github.io/stubpy/guides/ci.html)
- [API reference](https://wzjoriv.github.io/stubpy/reference/api.html)
- [Architecture](https://wzjoriv.github.io/stubpy/explanation/architecture.html) and [comparison with other tools](https://wzjoriv.github.io/stubpy/explanation/comparison.html)
- [Contributing](https://wzjoriv.github.io/stubpy/contributing.html)

## License

MIT. See [LICENSE](LICENSE).
