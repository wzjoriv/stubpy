# svgraster (stubpy corpus)

A small set of compiled raster primitives, one per binding style, kept as
real-world input for stubpy's compiled-module tests
(`tests/compiled/test_svgraster.py`) and `python scripts/dev.py stubpy raster`.

| Module | Binding style |
|---|---|
| `_scanline.c` | CPython C API (`__text_signature__`, getset, buffer protocol) |
| `_codec.pyx` | Cython with `embedsignature` (cpdef enums, cdef class, exception) |
| `_pattern.pyx` | Cython without `embedsignature` |
| `_filters.cpp` | pybind11 (overloads, `py::enum_`, properties, keyword-only) |
| `_composite.cpp` | nanobind (`nb::ndarray`, `kw_only`, enums) |
| `_jit.py` | numba, with numpy fallbacks |

`raster/` and `filters/` are a thin Python layer that subclasses the compiled
classes and forwards `**kwargs` into them. numpy is the only dependency.

```bash
python setup.py build_ext --inplace     # OpenMP is optional; SVGRASTER_NO_OPENMP=1 skips it
python -m pytest -q
```

Or, from the repository root: `python scripts/dev.py demos svgraster build`.
