# stubpy

Generate accurate `.pyi` stubs for your Python package, with `**kwargs` and `*args` traced back to the parameters they forward to. Standard library only.

[![PyPI](https://img.shields.io/pypi/v/stubpy)](https://pypi.org/project/stubpy/)
[![Python](https://img.shields.io/pypi/pyversions/stubpy)](https://pypi.org/project/stubpy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-wzjoriv.github.io%2Fstubpy-blue)](https://wzjoriv.github.io/stubpy)

## Features

| Feature | What you get |
|---|---|
| `**kwargs` / `*args` back-tracing | Forwarded parameters written into the stub signature. |
| Runtime, AST or auto | Import for precision, parse for safety, or fall back. |
| Alias preservation | Aliases like `Length` stay as written, with imports added. |
| Special classes | Dedicated stubs for dataclasses, enums, TypedDict, NamedTuple, Generic, overloads. |
| Compiled extensions | C API, Cython, pybind11 and nanobind modules, including docstrings. |
| Package generation | One command stubs a whole tree, with `__init__.pyi`. |
| Check mode | `stubpy check` exits `1` on missing or stale stubs. |
| Hints | `@hint.signature`, `@hint.returns`, `@hint.ignore` for what introspection misses. |
| Incremental merge | Rewrites only the marked region and keeps hand edits. |
| Configuration | `[tool.stubpy]` in `pyproject.toml`; flags override it. |
| Version branches | `sys.version_info` / `sys.platform` blocks kept, as typeshed does. |
| Lazy attributes | Names behind a module `__getattr__` become explicit. |
| Pre-commit hooks | `stubpy-check` and `stubpy-generate`, ready to use. |

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
- [API reference](https://wzjoriv.github.io/stubpy/reference/api/index.html)
- [Comparison with other tools](https://wzjoriv.github.io/stubpy/explanation/comparison.html)
- [Contributing](https://wzjoriv.github.io/stubpy/contributing.html)

## License

MIT. See [LICENSE](LICENSE).
