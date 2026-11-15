# Demos

Two small, working projects that stubpy's tests and docs use as real-world input.

| Project | What it is | What it exercises in stubpy |
|---|---|---|
| [`svgwriter/`](svgwriter/) | Pure-Python library for writing and parsing SVG 1.1 documents (all 80 elements, path data, transforms, colors, filters, animation). Stdlib only. | Deep `**kwargs` chains through cooperative mixins (`Rect` has ~9 classes in its MRO), `cls(**kwargs)` factories, cross-module forwarding, Generic / ParamSpec / Concatenate, overloads, Protocols, ABCs, dataclasses (`InitVar`, `kw_only`, `slots`), every enum flavour, descriptors, `__init_subclass__` keywords, `functools.partial` / `lru_cache` / `singledispatch`, module `__getattr__`, async helpers, version-guarded PEP 695, dynamic `__all__`. |
| [`svgraster/`](svgraster/) | SVG 1.1 rasterizer that renders to numpy arrays, with native layers built every common way. numpy is its only dependency; every native layer has a numpy fallback. | Compiled modules: CPython C API (`__text_signature__`, getset, buffer protocol), Cython with and without `embedsignature`, pybind11 (overloads, `py::enum_`, properties, `py::array_t`), nanobind (`__nb_signature__`, `nb::ndarray`, `kw_only`), numba dispatchers, Python subclasses of compiled classes and `**kwargs` forwarded into compiled callables. |

Each project has its own `pyproject.toml`, `README.md` and `tests/`:

```bash
cd demos/svgwriter && python -m pytest -q
cd demos/svgraster && python setup.py build_ext --inplace && python -m pytest -q
```
