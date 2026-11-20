# svgraster (stubpy corpus)

A small set of compiled raster primitives, one per binding style, kept as
real-world input for stubpy's compiled-module tests
(`tests/compiled/test_svgraster.py`) and `python scripts/dev.py stubpy raster`.

| Module | Binding style |
|---|---|
| `_scanline.c` | CPython C API (`__text_signature__`, getset, buffer protocol) |
| `_geometry.c` | CPython C API without signature docstrings (`PyArg_ParseTuple`, `kwlist`, `METH_O`, `METH_NOARGS`, members, getsets) |
| `_codec.pyx` | Cython with `embedsignature` (cpdef enums, cdef class, exception) |
| `_pattern.pyx` | Cython without `embedsignature` |
| `_filters.cpp` | pybind11 (overloads, `py::enum_`, properties, keyword-only) |
| `_composite.cpp` | nanobind (`nb::ndarray`, `kw_only`, enums) |
| `_jit.py` | numba, with numpy fallbacks |
| `raster/levels.py` | pure Python wrappers that forward `**kwargs` to third-party callables (`numpy.clip`, `numpy.asarray`, the `numpy.multiply` ufunc) |
| `plugins/` | a subpackage whose `__init__.py` imports a missing optional dependency (`svgraster_gpu`), next to a pure sibling module (`gamma.py`) |

`raster/` and `filters/` are a thin Python layer that subclasses the compiled
classes and forwards `**kwargs` into them. numpy is the only dependency.

```bash
python setup.py build_ext --inplace     # OpenMP is optional; SVGRASTER_NO_OPENMP=1 skips it
python -m pytest -q
```

Or, from the repository root: `python scripts/dev.py corpora svgraster build`.

`plugins/` is a broken parent on purpose: importing it always raises, so stubpy falls back to source analysis
for it and its siblings. Multi-platform builds are not stored in the repository: the tests copy `_pattern.pyx`
and the built module into a temporary package, add placeholder files for other platforms and ABIs, and check
that only the running interpreter's build is stubbed (`tests/compiled/test_corpus_additions.py`).
