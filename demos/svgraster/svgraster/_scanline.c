/* Anti-aliased polygon coverage with the CPython C API and the buffer protocol. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "_native/scanline_core.h"

#define DEFAULT_SAMPLES 4
#define MAX_SAMPLES 256
#define POINT_BYTES (2 * sizeof(double))
#define SCANLINE_VERSION "1.0"

static int is_double_format(const char *fmt) {
    if (fmt == NULL) return 1;
    if (fmt[0] == '<' || fmt[0] == '=' || fmt[0] == '@') fmt++;
    return strcmp(fmt, "d") == 0;
}

static int is_float_format(const char *fmt) {
    if (fmt == NULL) return 0;
    if (fmt[0] == '<' || fmt[0] == '=' || fmt[0] == '@') fmt++;
    return strcmp(fmt, "f") == 0;
}

static int collect_edges(PyObject *polygons, int height, int samples, EdgeList *list) {
    PyObject *seq = PySequence_Fast(polygons, "polygons must be a sequence of buffers");
    if (!seq) return -1;
    long long k_total = (long long)height * samples;
    for (Py_ssize_t p = 0; p < PySequence_Fast_GET_SIZE(seq); p++) {
        Py_buffer view;
        if (PyObject_GetBuffer(PySequence_Fast_GET_ITEM(seq, p), &view, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) {
            Py_DECREF(seq);
            return -1;
        }
        if (!is_double_format(view.format) || view.itemsize != sizeof(double) || view.len % POINT_BYTES) {
            PyBuffer_Release(&view);
            Py_DECREF(seq);
            PyErr_SetString(PyExc_TypeError, "each polygon must be a contiguous float64 (N, 2) buffer");
            return -1;
        }
        Py_ssize_t n = view.len / (Py_ssize_t)POINT_BYTES;
        int rc = n >= 2 ? edges_append_polygon(list, (const double *)view.buf, n, k_total, samples) : 0;
        PyBuffer_Release(&view);
        if (rc < 0) {
            Py_DECREF(seq);
            PyErr_NoMemory();
            return -1;
        }
    }
    Py_DECREF(seq);
    return 0;
}

static int fill_into(float *buf, int width, int height, PyObject *polygons, int rule, int samples) {
    if (rule != RULE_NONZERO && rule != RULE_EVENODD) {
        PyErr_SetString(PyExc_ValueError, "rule must be 0 (nonzero) or 1 (evenodd)");
        return -1;
    }
    if (samples < 1 || samples > MAX_SAMPLES) {
        PyErr_SetString(PyExc_ValueError, "samples out of range");
        return -1;
    }
    EdgeList list = {NULL, 0, 0};
    if (collect_edges(polygons, height, samples, &list) < 0) {
        free(list.items);
        return -1;
    }
    int rc;
    Py_BEGIN_ALLOW_THREADS
    rc = rasterize_edges(buf, width, &list, rule, samples);
    Py_END_ALLOW_THREADS
    free(list.items);
    if (rc < 0) PyErr_NoMemory();
    return rc;
}

static int get_coverage_buffer(PyObject *obj, Py_buffer *view) {
    if (PyObject_GetBuffer(obj, view, PyBUF_WRITABLE | PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) return -1;
    if (!is_float_format(view->format) || view->ndim != 2) {
        PyBuffer_Release(view);
        PyErr_SetString(PyExc_TypeError, "coverage must be a writable contiguous float32 2-D buffer");
        return -1;
    }
    return 0;
}

/* ---- module functions ---- */

PyDoc_STRVAR(fill_polygons_doc,
"fill_polygons($module, out, polygons, rule=0, samples=4, /)\n--\n\n"
"Accumulate anti-aliased coverage of polygons into a float32 (H, W) buffer.\n\n"
"rule is 0 for nonzero and 1 for evenodd; samples is sub-scanlines per row.");

static PyObject *fill_polygons(PyObject *module, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs < 2 || nargs > 4) {
        PyErr_SetString(PyExc_TypeError, "fill_polygons expects 2 to 4 positional arguments");
        return NULL;
    }
    int rule = RULE_NONZERO, samples = DEFAULT_SAMPLES;
    if (nargs > 2 && (rule = (int)PyLong_AsLong(args[2])) == -1 && PyErr_Occurred()) return NULL;
    if (nargs > 3 && (samples = (int)PyLong_AsLong(args[3])) == -1 && PyErr_Occurred()) return NULL;
    Py_buffer view;
    if (get_coverage_buffer(args[0], &view) < 0) return NULL;
    int rc = fill_into((float *)view.buf, (int)view.shape[1], (int)view.shape[0], args[1], rule, samples);
    PyBuffer_Release(&view);
    if (rc < 0) return NULL;
    Py_RETURN_NONE;
}

PyDoc_STRVAR(polygon_area_doc,
"polygon_area($module, points, /)\n--\n\n"
"Signed shoelace area of a float64 (N, 2) point buffer.");

static PyObject *polygon_area(PyObject *module, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs != 1) {
        PyErr_SetString(PyExc_TypeError, "polygon_area expects exactly one argument");
        return NULL;
    }
    Py_buffer view;
    if (PyObject_GetBuffer(args[0], &view, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) return NULL;
    if (!is_double_format(view.format) || view.len % POINT_BYTES) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_TypeError, "points must be a contiguous float64 (N, 2) buffer");
        return NULL;
    }
    const double *p = (const double *)view.buf;
    Py_ssize_t n = view.len / (Py_ssize_t)POINT_BYTES;
    double acc = 0.0;
    for (Py_ssize_t i = 0; i < n; i++) {
        Py_ssize_t j = (i + 1) % n;
        acc += p[2 * i] * p[2 * j + 1] - p[2 * j] * p[2 * i + 1];
    }
    PyBuffer_Release(&view);
    return PyFloat_FromDouble(0.5 * acc);
}

PyDoc_STRVAR(clamp_unit_doc,
"Clamp every value of a writable float32 buffer into [0, 1] in place.\n\n"
"Returns None.");

static PyObject *clamp_unit(PyObject *module, PyObject *obj) {
    Py_buffer view;
    if (PyObject_GetBuffer(obj, &view, PyBUF_WRITABLE | PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) return NULL;
    if (!is_float_format(view.format)) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_TypeError, "expected a float32 buffer");
        return NULL;
    }
    float *v = (float *)view.buf;
    Py_ssize_t n = view.len / (Py_ssize_t)sizeof(float);
    for (Py_ssize_t i = 0; i < n; i++) v[i] = v[i] < 0.0f ? 0.0f : (v[i] > 1.0f ? 1.0f : v[i]);
    PyBuffer_Release(&view);
    Py_RETURN_NONE;
}

PyDoc_STRVAR(coverage_sum_doc,
"coverage_sum(buffer) -> float\n\n"
"Sum of a float32 coverage buffer, i.e. the covered area in pixels.");

static PyObject *coverage_sum(PyObject *module, PyObject *obj) {
    Py_buffer view;
    if (PyObject_GetBuffer(obj, &view, PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) < 0) return NULL;
    if (!is_float_format(view.format)) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_TypeError, "expected a float32 buffer");
        return NULL;
    }
    const float *v = (const float *)view.buf;
    double acc = 0.0;
    for (Py_ssize_t i = 0; i < view.len / (Py_ssize_t)sizeof(float); i++) acc += v[i];
    PyBuffer_Release(&view);
    return PyFloat_FromDouble(acc);
}

PyDoc_STRVAR(version_doc, "version() -> str\n\nThe scanline module version.");

static PyObject *version(PyObject *module, PyObject *unused) {
    return PyUnicode_FromString(SCANLINE_VERSION);
}

/* ---- Rasterizer type ---- */

typedef struct {
    PyObject_HEAD
    float *buf;
    int width;
    int height;
    int samples;
    Py_ssize_t exports;
} RasterizerObject;

static void Rasterizer_dealloc(RasterizerObject *self) {
    free(self->buf);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static int Rasterizer_init(RasterizerObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"width", "height", "samples", NULL};
    int width, height, samples = DEFAULT_SAMPLES;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "ii|i:Rasterizer", kwlist, &width, &height, &samples)) return -1;
    if (width < 0 || height < 0) {
        PyErr_SetString(PyExc_ValueError, "size must be non-negative");
        return -1;
    }
    if (samples < 1 || samples > MAX_SAMPLES) {
        PyErr_SetString(PyExc_ValueError, "samples out of range");
        return -1;
    }
    if (self->exports > 0) {
        PyErr_SetString(PyExc_BufferError, "cannot resize while the coverage is exported");
        return -1;
    }
    float *buf = (float *)calloc((size_t)width * (size_t)height + 1, sizeof(float));
    if (!buf) {
        PyErr_NoMemory();
        return -1;
    }
    free(self->buf);
    self->buf = buf;
    self->width = width;
    self->height = height;
    self->samples = samples;
    return 0;
}

static int Rasterizer_getbuffer(RasterizerObject *self, Py_buffer *view, int flags) {
    if (self->buf == NULL) {
        PyErr_SetString(PyExc_BufferError, "Rasterizer is not initialized");
        return -1;
    }
    static const char fmt[] = "f";
    view->obj = Py_NewRef(self);
    view->buf = self->buf;
    view->len = (Py_ssize_t)self->width * self->height * (Py_ssize_t)sizeof(float);
    view->readonly = 0;
    view->itemsize = sizeof(float);
    view->format = (flags & PyBUF_FORMAT) ? (char *)fmt : NULL;
    view->ndim = 2;
    view->shape = (Py_ssize_t *)PyMem_Malloc(4 * sizeof(Py_ssize_t));
    if (!view->shape) {
        Py_CLEAR(view->obj);
        PyErr_NoMemory();
        return -1;
    }
    view->strides = view->shape + 2;
    view->shape[0] = self->height;
    view->shape[1] = self->width;
    view->strides[0] = (Py_ssize_t)self->width * (Py_ssize_t)sizeof(float);
    view->strides[1] = sizeof(float);
    view->suboffsets = NULL;
    view->internal = NULL;
    self->exports++;
    return 0;
}

static void Rasterizer_releasebuffer(RasterizerObject *self, Py_buffer *view) {
    PyMem_Free(view->shape);
    self->exports--;
}

static PyBufferProcs Rasterizer_as_buffer = {
    (getbufferproc)Rasterizer_getbuffer,
    (releasebufferproc)Rasterizer_releasebuffer,
};

static int ready(RasterizerObject *self) {
    if (self->buf == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Rasterizer.__init__ was not called");
        return 0;
    }
    return 1;
}

PyDoc_STRVAR(Rasterizer_fill_doc,
"fill($self, polygons, rule=0)\n--\n\n"
"Accumulate the coverage of polygons (float64 (N, 2) buffers).");

static PyObject *Rasterizer_fill(RasterizerObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"polygons", "rule", NULL};
    PyObject *polygons;
    int rule = RULE_NONZERO;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|i:fill", kwlist, &polygons, &rule)) return NULL;
    if (!ready(self)) return NULL;
    if (fill_into(self->buf, self->width, self->height, polygons, rule, self->samples) < 0) return NULL;
    Py_ssize_t n = (Py_ssize_t)self->width * self->height;
    for (Py_ssize_t i = 0; i < n; i++) self->buf[i] = self->buf[i] > 1.0f ? 1.0f : self->buf[i];
    Py_RETURN_NONE;
}

PyDoc_STRVAR(Rasterizer_clear_doc, "clear($self, /)\n--\n\nReset all coverage to zero.");

static PyObject *Rasterizer_clear(RasterizerObject *self, PyObject *unused) {
    if (!ready(self)) return NULL;
    memset(self->buf, 0, (size_t)self->width * (size_t)self->height * sizeof(float));
    Py_RETURN_NONE;
}

PyDoc_STRVAR(Rasterizer_coverage_doc, "coverage($self, /)\n--\n\nA writable memoryview of the coverage buffer.");

static PyObject *Rasterizer_coverage(RasterizerObject *self, PyObject *unused) {
    if (!ready(self)) return NULL;
    return PyMemoryView_FromObject((PyObject *)self);
}

PyDoc_STRVAR(Rasterizer_total_doc, "Sum of all coverage (the covered area in pixels).");

static PyObject *Rasterizer_total(RasterizerObject *self, PyObject *unused) {
    if (!ready(self)) return NULL;
    double acc = 0.0;
    for (Py_ssize_t i = 0; i < (Py_ssize_t)self->width * self->height; i++) acc += self->buf[i];
    return PyFloat_FromDouble(acc);
}

PyDoc_STRVAR(Rasterizer_from_shape_doc,
"from_shape($type, shape, samples=4)\n--\n\n"
"Build a Rasterizer from a (height, width) shape tuple.");

static PyObject *Rasterizer_from_shape(PyObject *cls, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"shape", "samples", NULL};
    int height, width, samples = DEFAULT_SAMPLES;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "(ii)|i:from_shape", kwlist, &height, &width, &samples)) return NULL;
    return PyObject_CallFunction(cls, "iii", width, height, samples);
}

static PyMethodDef Rasterizer_methods[] = {
    {"fill", (PyCFunction)(void (*)(void))Rasterizer_fill, METH_VARARGS | METH_KEYWORDS, Rasterizer_fill_doc},
    {"clear", (PyCFunction)Rasterizer_clear, METH_NOARGS, Rasterizer_clear_doc},
    {"coverage", (PyCFunction)Rasterizer_coverage, METH_NOARGS, Rasterizer_coverage_doc},
    {"total", (PyCFunction)Rasterizer_total, METH_NOARGS, Rasterizer_total_doc},
    {"from_shape", (PyCFunction)(void (*)(void))Rasterizer_from_shape, METH_VARARGS | METH_KEYWORDS | METH_CLASS,
     Rasterizer_from_shape_doc},
    {NULL, NULL, 0, NULL},
};

static PyObject *Rasterizer_get_width(RasterizerObject *self, void *closure) {
    return PyLong_FromLong(self->width);
}

static PyObject *Rasterizer_get_height(RasterizerObject *self, void *closure) {
    return PyLong_FromLong(self->height);
}

static PyObject *Rasterizer_get_samples(RasterizerObject *self, void *closure) {
    return PyLong_FromLong(self->samples);
}

static int Rasterizer_set_samples(RasterizerObject *self, PyObject *value, void *closure) {
    if (value == NULL) {
        PyErr_SetString(PyExc_AttributeError, "cannot delete samples");
        return -1;
    }
    long v = PyLong_AsLong(value);
    if (v == -1 && PyErr_Occurred()) return -1;
    if (v < 1 || v > MAX_SAMPLES) {
        PyErr_SetString(PyExc_ValueError, "samples out of range");
        return -1;
    }
    self->samples = (int)v;
    return 0;
}

static PyGetSetDef Rasterizer_getset[] = {
    {"width", (getter)Rasterizer_get_width, NULL, "Columns in the coverage buffer.", NULL},
    {"height", (getter)Rasterizer_get_height, NULL, "Rows in the coverage buffer.", NULL},
    {"samples", (getter)Rasterizer_get_samples, (setter)Rasterizer_set_samples, "Sub-scanlines per pixel row.",
     NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

PyDoc_STRVAR(Rasterizer_doc,
"Rasterizer(width, height, samples=4)\n--\n\n"
"An accumulating float32 coverage canvas exposed through the buffer protocol.");

static PyTypeObject RasterizerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "svgraster._scanline.Rasterizer",
    .tp_basicsize = sizeof(RasterizerObject),
    .tp_dealloc = (destructor)Rasterizer_dealloc,
    .tp_as_buffer = &Rasterizer_as_buffer,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_doc = Rasterizer_doc,
    .tp_methods = Rasterizer_methods,
    .tp_getset = Rasterizer_getset,
    .tp_init = (initproc)Rasterizer_init,
    .tp_new = PyType_GenericNew,
};

static PyMethodDef module_methods[] = {
    {"fill_polygons", (PyCFunction)(void (*)(void))fill_polygons, METH_FASTCALL, fill_polygons_doc},
    {"polygon_area", (PyCFunction)(void (*)(void))polygon_area, METH_FASTCALL, polygon_area_doc},
    {"clamp_unit", (PyCFunction)clamp_unit, METH_O, clamp_unit_doc},
    {"coverage_sum", (PyCFunction)coverage_sum, METH_O, coverage_sum_doc},
    {"version", (PyCFunction)version, METH_NOARGS, version_doc},
    {NULL, NULL, 0, NULL},
};

PyDoc_STRVAR(module_doc, "Anti-aliased polygon scanline filling (CPython C API).");

static struct PyModuleDef scanline_module = {
    PyModuleDef_HEAD_INIT, "_scanline", module_doc, -1, module_methods,
};

PyMODINIT_FUNC PyInit__scanline(void) {
    if (PyType_Ready(&RasterizerType) < 0) return NULL;
    PyObject *m = PyModule_Create(&scanline_module);
    if (!m) return NULL;
    if (PyModule_AddObjectRef(m, "Rasterizer", (PyObject *)&RasterizerType) < 0 ||
        PyModule_AddIntConstant(m, "NONZERO", RULE_NONZERO) < 0 ||
        PyModule_AddIntConstant(m, "EVENODD", RULE_EVENODD) < 0 ||
        PyModule_AddIntConstant(m, "MAX_SAMPLES", MAX_SAMPLES) < 0 ||
        PyModule_AddObjectRef(m, "HAVE_OPENMP", Py_False) < 0) {
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
