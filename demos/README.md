# Demos

Two small projects that stubpy's tests and docs use as real-world input. Neither is a product: they are
trimmed to the constructs stubpy needs.

| Project | What it is | What it exercises in stubpy |
|---|---|---|
| [`svgwriter/`](svgwriter/) | About 35 pure-Python modules: elements, path data, transforms, colors, a writer. Stdlib only. | Deep `**kwargs` chains through cooperative mixins, `cls(**kwargs)` factories, shortcut methods with local imports, overloads with reflected and in-place operators, Generic / ParamSpec / Concatenate, Protocols, ABCs, dataclasses (`InitVar`, `kw_only`), NamedTuple, TypedDict, enum flavours, descriptors, `__init_subclass__` keywords, `functools.partial` / `lru_cache` / `singledispatch`, module `__getattr__`, async helpers, version-guarded PEP 695, an optional skia import. |
| [`svgraster/`](svgraster/) | Five native modules (one per binding style) plus a numba module and a thin Python layer. numpy is the only dependency. | Compiled modules: CPython C API (`__text_signature__`, getset, buffer protocol), Cython with and without `embedsignature`, pybind11 (overloads, `py::enum_`, properties), nanobind (`nb::ndarray`, `kw_only`), numba, Python subclasses of compiled classes and `**kwargs` forwarded into compiled callables. |

`svgraster` has its own tests and a build step; `svgwriter` is exercised only through stubpy's tests:

```bash
python scripts/dev.py demos svgraster build        # build the native modules in place
cd demos/svgraster && python -m pytest -q
python scripts/dev.py stubpy demo                  # stub the svgwriter corpus and list what changed
python scripts/dev.py stubpy raster                # stub svgraster, compiled modules included
```
