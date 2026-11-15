/* TrueType simple-glyph decoding (flags, delta coordinates) with the CPython C API. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define ON_CURVE 0x01
#define X_SHORT 0x02
#define Y_SHORT 0x04
#define REPEAT 0x08
#define X_SAME 0x10
#define Y_SAME 0x20
#define HEADER_SIZE 10
#define FIELDS_PER_POINT 3
#define MAX_POINTS 65536

typedef struct {
    const uint8_t *data;
    Py_ssize_t size;
    Py_ssize_t pos;
} Cursor;

static int need(Cursor *c, Py_ssize_t n) {
    if (c->pos + n > c->size) {
        PyErr_SetString(PyExc_ValueError, "glyph data runs past the end of the font");
        return -1;
    }
    return 0;
}

static int read_u8(Cursor *c, int *out) {
    if (need(c, 1) < 0) return -1;
    *out = c->data[c->pos++];
    return 0;
}

static int read_i16(Cursor *c, int *out) {
    if (need(c, 2) < 0) return -1;
    *out = (int16_t)((c->data[c->pos] << 8) | c->data[c->pos + 1]);
    c->pos += 2;
    return 0;
}

static int read_u16(Cursor *c, int *out) {
    if (need(c, 2) < 0) return -1;
    *out = (c->data[c->pos] << 8) | c->data[c->pos + 1];
    c->pos += 2;
    return 0;
}

static int read_coords(Cursor *c, const uint8_t *flags, int n, int32_t *out, int axis) {
    int shortbit = axis ? Y_SHORT : X_SHORT, samebit = axis ? Y_SAME : X_SAME, value = 0, d;
    for (int i = 0; i < n; i++) {
        if (flags[i] & shortbit) {
            if (read_u8(c, &d) < 0) return -1;
            value += (flags[i] & samebit) ? d : -d;
        } else if (!(flags[i] & samebit)) {
            if (read_i16(c, &d) < 0) return -1;
            value += d;
        }
        out[i * FIELDS_PER_POINT + axis] = value;
    }
    return 0;
}

static PyObject *decode(const uint8_t *data, Py_ssize_t size, Py_ssize_t offset) {
    Cursor c = {data, size, offset};
    int contours, v;
    if (offset < 0 || read_i16(&c, &contours) < 0) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, "offset out of range");
        return NULL;
    }
    if (contours < 0) {
        PyErr_SetString(PyExc_ValueError, "not a simple glyph");
        return NULL;
    }
    c.pos += HEADER_SIZE - 2;
    PyObject *ends = PyTuple_New(contours);
    if (!ends) return NULL;
    int last = -1;
    for (int i = 0; i < contours; i++) {
        if (read_u16(&c, &v) < 0) {
            Py_DECREF(ends);
            return NULL;
        }
        last = v;
        PyTuple_SET_ITEM(ends, i, PyLong_FromLong(v));
    }
    int n = last + 1;
    if (n > MAX_POINTS || read_u16(&c, &v) < 0) {
        if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, "too many points in glyph");
        Py_DECREF(ends);
        return NULL;
    }
    c.pos += v;
    uint8_t *flags = (uint8_t *)malloc(n > 0 ? (size_t)n : 1);
    int32_t *pts = (int32_t *)calloc(n > 0 ? (size_t)n * FIELDS_PER_POINT : 1, sizeof(int32_t));
    if (!flags || !pts) {
        free(flags);
        free(pts);
        Py_DECREF(ends);
        return PyErr_NoMemory();
    }
    int ok = 0;
    for (int i = 0; i < n;) {
        int f, repeat = 0;
        if (read_u8(&c, &f) < 0) goto done;
        flags[i++] = (uint8_t)f;
        if (f & REPEAT) {
            if (read_u8(&c, &repeat) < 0) goto done;
            for (int k = 0; k < repeat && i < n; k++) flags[i++] = (uint8_t)f;
        }
    }
    if (read_coords(&c, flags, n, pts, 0) < 0 || read_coords(&c, flags, n, pts, 1) < 0) goto done;
    for (int i = 0; i < n; i++) pts[i * FIELDS_PER_POINT + 2] = flags[i] & ON_CURVE;
    ok = 1;
done:
    free(flags);
    if (!ok) {
        free(pts);
        Py_DECREF(ends);
        return NULL;
    }
    PyObject *packed = PyBytes_FromStringAndSize((const char *)pts, (Py_ssize_t)n * FIELDS_PER_POINT * 4);
    free(pts);
    if (!packed) {
        Py_DECREF(ends);
        return NULL;
    }
    return Py_BuildValue("(NN)", ends, packed);
}

PyDoc_STRVAR(simple_glyph_doc,
"simple_glyph($module, data, offset, /)\n--\n\n"
"Decode the simple glyph at ``offset``: ``(contour end indices, packed int32 x, y, on-curve triples)``.");

static PyObject *simple_glyph(PyObject *module, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "simple_glyph expects (data, offset)");
        return NULL;
    }
    Py_ssize_t offset = PyLong_AsSsize_t(args[1]);
    if (offset == -1 && PyErr_Occurred()) return NULL;
    Py_buffer view;
    if (PyObject_GetBuffer(args[0], &view, PyBUF_SIMPLE) < 0) return NULL;
    PyObject *result = decode((const uint8_t *)view.buf, view.len, offset);
    PyBuffer_Release(&view);
    return result;
}

PyDoc_STRVAR(glyph_header_doc,
"glyph_header($module, data, offset, /)\n--\n\n"
"``(number of contours, x_min, y_min, x_max, y_max)`` of the glyph at ``offset``.");

static PyObject *glyph_header(PyObject *module, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "glyph_header expects (data, offset)");
        return NULL;
    }
    Py_ssize_t offset = PyLong_AsSsize_t(args[1]);
    if (offset == -1 && PyErr_Occurred()) return NULL;
    Py_buffer view;
    if (PyObject_GetBuffer(args[0], &view, PyBUF_SIMPLE) < 0) return NULL;
    Cursor c = {(const uint8_t *)view.buf, view.len, offset};
    int v[5];
    for (int i = 0; i < 5; i++) {
        if (offset < 0 || read_i16(&c, &v[i]) < 0) {
            PyBuffer_Release(&view);
            if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, "offset out of range");
            return NULL;
        }
    }
    PyBuffer_Release(&view);
    return Py_BuildValue("(iiiii)", v[0], v[1], v[2], v[3], v[4]);
}

PyDoc_STRVAR(version_doc, "Version string of the glyph decoder.");

static PyObject *version(PyObject *module, PyObject *unused) { return PyUnicode_FromString("1.0"); }

static PyMethodDef module_methods[] = {
    {"simple_glyph", (PyCFunction)(void (*)(void))simple_glyph, METH_FASTCALL, simple_glyph_doc},
    {"glyph_header", (PyCFunction)(void (*)(void))glyph_header, METH_FASTCALL, glyph_header_doc},
    {"version", (PyCFunction)version, METH_NOARGS, version_doc},
    {NULL, NULL, 0, NULL},
};

PyDoc_STRVAR(module_doc, "TrueType glyf decoding (CPython C API).");

static struct PyModuleDef glyf_module = {
    PyModuleDef_HEAD_INIT, "_glyf", module_doc, -1, module_methods,
};

PyMODINIT_FUNC PyInit__glyf(void) {
    PyObject *m = PyModule_Create(&glyf_module);
    if (!m) return NULL;
    if (PyModule_AddIntConstant(m, "ON_CURVE", ON_CURVE) < 0 || PyModule_AddIntConstant(m, "REPEAT", REPEAT) < 0 ||
        PyModule_AddObjectRef(m, "HAVE_OPENMP", Py_False) < 0) {
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
