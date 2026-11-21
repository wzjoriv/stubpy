/* Small 2-D geometry helpers with the CPython C API and no signature docstrings. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <math.h>

typedef struct {
    PyObject_HEAD
    double x;
    double y;
    int id;
    PyObject *label;
} PointObject;

static int next_id = 0;

static int Point_init(PointObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"x", "y", NULL};
    double x = 0.0, y = 0.0;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|dd:Point", kwlist, &x, &y)) return -1;
    self->x = x;
    self->y = y;
    self->id = next_id++;
    return 0;
}

static void Point_dealloc(PointObject *self) {
    Py_XDECREF(self->label);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *Point_scale(PointObject *self, PyObject *factor) {
    double f = PyFloat_AsDouble(factor);
    if (f == -1.0 && PyErr_Occurred()) return NULL;
    self->x *= f;
    self->y *= f;
    Py_RETURN_NONE;
}

static PyObject *Point_translate(PointObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"dx", "dy", NULL};
    double dx, dy = 0.0;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "d|d:translate", kwlist, &dx, &dy)) return NULL;
    self->x += dx;
    self->y += dy;
    Py_RETURN_NONE;
}

static PyObject *Point_as_tuple(PointObject *self, PyObject *Py_UNUSED(ignored)) {
    return Py_BuildValue("(dd)", self->x, self->y);
}

static PyObject *Point_get_norm(PointObject *self, void *closure) {
    return PyFloat_FromDouble(hypot(self->x, self->y));
}

static PyObject *Point_get_label(PointObject *self, void *closure) {
    if (self->label == NULL) return PyUnicode_FromString("");
    return PyUnicode_FromObject(self->label);
}

static int Point_set_label(PointObject *self, PyObject *value, void *closure) {
    if (value != NULL && !PyUnicode_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "label must be a str");
        return -1;
    }
    Py_XINCREF(value);
    Py_XSETREF(self->label, value);
    return 0;
}

static PyMethodDef Point_methods[] = {
    {"scale", (PyCFunction)Point_scale, METH_O, NULL},
    {"translate", (PyCFunction)(void (*)(void))Point_translate, METH_VARARGS | METH_KEYWORDS, NULL},
    {"as_tuple", (PyCFunction)Point_as_tuple, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static PyMemberDef Point_members[] = {
    {"x", T_DOUBLE, offsetof(PointObject, x), 0, NULL},
    {"y", T_DOUBLE, offsetof(PointObject, y), 0, NULL},
    {"id", T_INT, offsetof(PointObject, id), READONLY, NULL},
    {NULL},
};

static PyGetSetDef Point_getset[] = {
    {"norm", (getter)Point_get_norm, NULL, NULL, NULL},
    {"label", (getter)Point_get_label, (setter)Point_set_label, NULL, NULL},
    {NULL},
};

static PyTypeObject PointType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "rasterlib._geometry.Point",
    .tp_basicsize = sizeof(PointObject),
    .tp_dealloc = (destructor)Point_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_methods = Point_methods,
    .tp_members = Point_members,
    .tp_getset = Point_getset,
    .tp_init = (initproc)Point_init,
    .tp_new = PyType_GenericNew,
};

static PyObject *distance(PyObject *self, PyObject *args) {
    PointObject *a, *b;
    if (!PyArg_ParseTuple(args, "O!O!:distance", &PointType, &a, &PointType, &b)) return NULL;
    return PyFloat_FromDouble(hypot(a->x - b->x, a->y - b->y));
}

static PyObject *lerp(PyObject *self, PyObject *args) {
    double start, end, t;
    if (!PyArg_ParseTuple(args, "ddd:lerp", &start, &end, &t)) return NULL;
    return PyFloat_FromDouble(start + (end - start) * t);
}

static PyObject *clamp(PyObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"value", "low", "high", "strict", NULL};
    double value, low = 0.0, high = 1.0;
    int strict = 0;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "d|dd$p:clamp", kwlist, &value, &low, &high, &strict)) return NULL;
    if (strict && (value < low || value > high)) {
        PyErr_SetString(PyExc_ValueError, "value out of range");
        return NULL;
    }
    return PyFloat_FromDouble(value < low ? low : value > high ? high : value);
}

static PyObject *quadrant(PyObject *self, PyObject *point) {
    if (!PyObject_TypeCheck(point, &PointType)) {
        PyErr_SetString(PyExc_TypeError, "expected a Point");
        return NULL;
    }
    PointObject *p = (PointObject *)point;
    return PyLong_FromLong(p->x >= 0 ? (p->y >= 0 ? 1 : 4) : (p->y >= 0 ? 2 : 3));
}

static PyObject *greet(PyObject *self, PyObject *args) {
    const char *name;
    if (!PyArg_ParseTuple(args, "z:greet", &name)) return NULL;
    if (name == NULL) Py_RETURN_NONE;
    return PyUnicode_FromFormat("hello %s", name);
}

static PyObject *origin_count(PyObject *self, PyObject *Py_UNUSED(ignored)) {
    return PyLong_FromLong(next_id);
}

static PyMethodDef module_methods[] = {
    {"distance", (PyCFunction)distance, METH_VARARGS, NULL},
    {"lerp", (PyCFunction)lerp, METH_VARARGS, NULL},
    {"clamp", (PyCFunction)(void (*)(void))clamp, METH_VARARGS | METH_KEYWORDS, NULL},
    {"quadrant", (PyCFunction)quadrant, METH_O, NULL},
    {"greet", (PyCFunction)greet, METH_VARARGS, NULL},
    {"origin_count", (PyCFunction)origin_count, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef geometry_module = {
    PyModuleDef_HEAD_INIT, "_geometry", NULL, -1, module_methods,
};

PyMODINIT_FUNC PyInit__geometry(void) {
    if (PyType_Ready(&PointType) < 0) return NULL;
    PyObject *m = PyModule_Create(&geometry_module);
    if (!m) return NULL;
    if (PyModule_AddObjectRef(m, "Point", (PyObject *)&PointType) < 0) {
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
