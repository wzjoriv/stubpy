"""C API sources: method tables, ``PyArg_Parse*`` formats and Argument Clinic blocks, read without compiling."""
from __future__ import annotations

import textwrap
import types

import pytest

from stubpy.compiled.capi import (
    c_sources,
    capi_attribute_types,
    capi_signatures,
    infer_return,
    parse_units,
    read_c_source,
)
from stubpy.compiled.capi._lexer import strip_comments

TABLES = textwrap.dedent('''\
    #define PY_SSIZE_T_CLEAN
    #include <Python.h>
    #include <structmember.h>
    #define LONG_MACRO(a) \\
        do_something(a)

    typedef struct { PyObject_HEAD double x; int n; PyObject *tag; } BoxObject;

    static int Box_init(BoxObject *self, PyObject *args, PyObject *kwds) {
        static char *kwlist[] = {"x", "n", NULL};
        if (!PyArg_ParseTupleAndKeywords(args, kwds, "d|i:Box", kwlist, &self->x, &self->n)) return -1;
        return 0;
    }

    /* {"hidden", (PyCFunction)hidden, METH_NOARGS, NULL}, */
    static PyObject *Box_area(BoxObject *self, PyObject *Py_UNUSED(ignored)) {
        return PyFloat_FromDouble(self->x * self->x);
    }

    static PyObject *Box_grow(BoxObject *self, PyObject *amount) {
        Py_RETURN_NONE;
    }

    static PyObject *Box_get_name(BoxObject *self, void *closure) {
        return PyUnicode_FromString("box");  // a str
    }

    static PyObject *Box_pair(BoxObject *self, PyObject *args) {
        return Py_BuildValue("(di)", self->x, self->n);
    }

    static PyMethodDef Box_methods[] = {
        {"area", (PyCFunction)Box_area, METH_NOARGS, NULL},
        {"grow", (PyCFunction)Box_grow, METH_O,
         "Grow the box."},
        {"pair", (PyCFunction)Box_pair, METH_VARARGS, NULL},
        {NULL, NULL, 0, NULL}
    };

    static PyMemberDef Box_members[] = {
        {"x", T_DOUBLE, offsetof(BoxObject, x), 0, NULL},
        {"n", Py_T_INT, offsetof(BoxObject, n), READONLY, NULL},
        {"tag", T_OBJECT_EX, offsetof(BoxObject, tag), 0, NULL},
        {NULL}
    };

    static PyGetSetDef Box_getset[] = {
        {"name", (getter)Box_get_name, NULL, NULL, NULL},
        {NULL}
    };

    static PyTypeObject BoxType = {
        PyVarObject_HEAD_INIT(NULL, 0)
        .tp_name = "pkg._ext.Box",
        .tp_methods = Box_methods,
        .tp_members = Box_members,
        .tp_getset = Box_getset,
        .tp_init = (initproc)Box_init,
    };

    static PyObject *scale(PyObject *self, PyObject *args, PyObject *kwds) {
        static char *kwlist[] = {"", "factor", "label", "flag", NULL};
        PyObject *box; double factor = 1.0; const char *label = NULL; int flag = 0;
        if (!PyArg_ParseTupleAndKeywords(args, kwds, "O!|dz$p:scale", kwlist,
                                         &BoxType, &box, &factor, &label, &flag))
            return NULL;
        if (flag) Py_RETURN_NONE;
        return PyLong_FromLong(1);
    }

    static PyObject *pack(PyObject *self, PyObject *args) {
        const char *data; Py_ssize_t size; PyObject *items; int a, b;
        if (!PyArg_ParseTuple(args, "s#O!(ii);bad arguments", &data, &size, &PyList_Type, &items, &a, &b))
            return NULL;
        return PyBytes_FromStringAndSize(data, size);
    }

    static PyObject *pick(PyObject *self, PyObject *args) {
        PyObject *first, *second = NULL;
        if (!PyArg_UnpackTuple(args, "pick", 1, 2, &first, &second)) return NULL;
        return first;
    }

    static PyObject *weird(PyObject *self, PyObject *args) {
        if (!PyArg_ParseTuple(args, "Q", &x)) return NULL;
        Py_RETURN_TRUE;
    }

    static PyMethodDef module_methods[] = {
        {"scale", (PyCFunction)(void (*)(void))scale, METH_VARARGS | METH_KEYWORDS, NULL},
        {"pack", pack, METH_VARARGS, NULL},
        {"pick", pick, METH_VARARGS, NULL},
        {"weird", weird, METH_VARARGS, NULL},
        {"missing", not_defined_here, METH_VARARGS, NULL},
        {NULL, NULL, 0, NULL}
    };
''')

CLINIC = textwrap.dedent('''\
    /*[clinic input]
    module _ext
    class _ext.Canvas "CanvasObject *" "&CanvasType"
    [clinic start generated code]*/

    /*[clinic input]
    _ext.blend -> double

        dst: object
        src: Py_buffer
        /
        alpha: double = 1.0
        *
        mode: str(accept={str, NoneType}) = None
        repeat: int = 2

    Blend src onto dst.
    [clinic start generated code]*/

    /*[clinic input]
    @classmethod
    _ext.Canvas.__new__ as canvas_new

        width: Py_ssize_t
        height: Py_ssize_t
        fill: object(subclass_of='&PyFloat_Type') = None

    [clinic start generated code]*/

    /*[clinic input]
    _ext.Canvas.clear

        self: self(type="CanvasObject *")
        *args: object
        strict: bool = False

    [clinic start generated code]*/

    static PyObject *_ext_Canvas_clear_impl(CanvasObject *self, PyObject *args, int strict) {
        Py_RETURN_NONE;
    }

    /*[clinic input]
    _ext.groups

        [
        x: int
        ]

    [clinic start generated code]*/
''')


@pytest.fixture(scope="module")
def tables():
    return read_c_source(TABLES)


def _render(module, name):
    return module.signatures[name].render()


def test_type_methods_from_tp_methods(tables):
    assert _render(tables, "Box.area") == "() -> float"
    assert _render(tables, "Box.grow") == "(amount: Any, /) -> None"
    assert _render(tables, "Box.pair") == "(*args: Any, **kwargs: Any) -> tuple[float, int]"


def test_tp_init_becomes_constructor(tables):
    assert _render(tables, "Box.__init__") == "(x: float, n: int = ...) -> None"


def test_keywords_optional_and_keyword_only(tables):
    assert _render(tables, "scale") == "(arg0: Box, /, factor: float = ..., label: str | None = ..., *, flag: bool = ...) -> int | None"


def test_parse_tuple_names_from_c_variables(tables):
    assert _render(tables, "pack") == "(data: str, items: list, arg2: tuple[int, int], /) -> bytes"
    assert _render(tables, "pick") == "(first: Any, second: Any = ..., /)"


def test_unreadable_format_keeps_return_only(tables):
    assert _render(tables, "weird") == "(*args: Any, **kwargs: Any) -> bool"
    assert "missing" not in tables.signatures
    assert "hidden" not in tables.signatures


def test_members_and_getsets(tables):
    assert tables.attributes == {"Box.x": "float", "Box.n": "int", "Box.tag": "Any", "Box.name": "str"}
    assert tables.classes == {"BoxType": "Box"}


def test_type_spec_slots():
    src = textwrap.dedent('''\
        static PyObject *Node_size(PyObject *self, PyObject *unused) { return PyLong_FromSsize_t(3); }
        static PyMethodDef node_methods[] = {{"size", Node_size, METH_NOARGS, NULL}, {NULL}};
        static PyType_Slot node_slots[] = {{Py_tp_methods, node_methods}, {0, NULL}};
        static PyType_Spec node_spec = {"pkg.Node", sizeof(NodeObject), 0, Py_TPFLAGS_DEFAULT, node_slots};
    ''')
    assert _render(read_c_source(src), "Node.size") == "() -> int"


def test_argument_clinic_blocks():
    found = read_c_source(CLINIC)
    assert _render(found, "blend") == (
        "(dst: Any, src: typing_extensions.Buffer, /, alpha: float = 1.0, *, mode: str | None = None, "
        "repeat: int = 2) -> float")
    assert _render(found, "Canvas.__init__") == "(width: int, height: int, fill: float | None = None) -> None"
    assert _render(found, "Canvas.clear") == "(*args: Any, strict: bool = False) -> None"
    assert "groups" not in found.signatures


@pytest.mark.parametrize(("fmt", "expected"), [
    ("ii|d:f", (["int", "int", "float"], [False, False, True], "f")),
    ("s*y#z|$U", (["str | typing_extensions.Buffer", "bytes", "str | None", "str"], [False] * 3 + [True], None)),
    ("es#O&", (["str", None], [False, False], None)),
])
def test_parse_units(fmt, expected):
    units, name = parse_units(fmt)
    assert ([u.type for u in units], [u.optional for u in units], name) == expected


def test_parse_units_unknown_is_none():
    assert parse_units("iQ") is None


@pytest.mark.parametrize(("body", "expected"), [
    ("Py_RETURN_NONE;", "None"),
    ("if (x) return NULL; return PyBool_FromLong(x);", "bool"),
    ('return Py_BuildValue("");', "None"),
    ('return Py_BuildValue("i", 1);', "int"),
    ('return Py_BuildValue("[ii]", 1, 2);', "list"),
    ("return result;", None),
    ("if (a) return PyLong_FromLong(1); return PyFloat_FromDouble(2);", None),
    ("return Py_NewRef(Py_None);", "None"),
])
def test_infer_return(body, expected):
    assert infer_return(body) == expected


def test_strip_comments_keeps_strings():
    assert strip_comments('a = "/* x */"; // gone\nb = \'"\'; /* c */') == 'a = "/* x */"; \nb = \'"\';  '


def _module(path):
    mod = types.ModuleType("pkg._ext")
    mod.__file__ = str(path)
    return mod


def test_sources_same_stem_src_and_pyinit(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "src").mkdir(parents=True)
    built = pkg / "_ext.cp312-win_amd64.pyd"
    built.write_bytes(b"")
    (pkg / "src" / "_ext.c").write_text(TABLES, encoding="utf-8")
    assert c_sources(built) == [pkg / "src" / "_ext.c"]
    (pkg / "src" / "_ext.c").unlink()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("PyMODINIT_FUNC PyInit__ext(void) { return NULL; }", encoding="utf-8")
    (tmp_path / "src" / "tables.c").write_text(TABLES, encoding="utf-8")
    (tmp_path / "src" / "other.c").write_text("PyMODINIT_FUNC PyInit_other(void) { return 0; }", encoding="utf-8")
    assert c_sources(built) == [tmp_path / "src" / "main.c", tmp_path / "src" / "tables.c"]
    assert capi_attribute_types(_module(built))["Box.x"] == "float"
    assert capi_signatures(_module(built))["Box.area"][0].returns == "float"


def test_cython_output_is_not_read(tmp_path):
    built = tmp_path / "_ext.so"
    built.write_bytes(b"")
    (tmp_path / "_ext.c").write_text("/* Generated by Cython 3.0 */\n" + TABLES, encoding="utf-8")
    assert c_sources(built) == []
    assert capi_signatures(_module(built)) == {}


GNU_STYLE = textwrap.dedent('''\
    static PyObject *
    py_scale(PyObject *self, PyObject *arg)
    {
        double f = PyFloat_AsDouble(arg);
        return PyFloat_FromDouble(f);
    }

    static PyObject *
    py_open(PyObject *self, PyObject *args, PyObject *kwargs)
    {
        static char *kwlist[] = {"data", "strict", NULL};
        Py_buffer data; int strict = 0;
        if (!PyArg_ParseTupleAndKeywords(args, kwargs, "y*|p", kwlist, &data, &strict))
            return NULL;
        return PyLong_FromLong(1);
    }

    PyMethodDef ext_methods[] = {
        {"scale", py_scale, METH_O, NULL},
        {"open", (PyCFunction)(void (*)(void))py_open, METH_VARARGS | METH_KEYWORDS, NULL},
        {NULL, NULL, 0, NULL},
    };
''')


def test_return_type_on_its_own_line():
    sigs = read_c_source(GNU_STYLE).signatures
    assert sigs["scale"].render() == "(arg: float, /) -> float"
    assert sigs["open"].render() == "(data: typing_extensions.Buffer, strict: bool = ...) -> int"


def test_sources_in_a_subfolder(tmp_path):
    built = tmp_path / "_ext.cp312-win_amd64.pyd"
    built.write_bytes(b"")
    (tmp_path / "_c").mkdir()
    (tmp_path / "_c" / "module.c").write_text("PyMODINIT_FUNC PyInit__ext(void) { return NULL; }", encoding="utf-8")
    (tmp_path / "_c" / "tables.c").write_text(GNU_STYLE, encoding="utf-8")
    assert c_sources(built) == [tmp_path / "_c" / "module.c", tmp_path / "_c" / "tables.c"]


def test_positional_c_parameter_pairs_by_position():
    from stubpy.compiled.pyx import merge_signature
    from stubpy.compiled.signatures import parse_signature

    live = parse_signature("info(fmt) -> tuple[str, int]")[1]
    source = read_c_source(GNU_STYLE).signatures["scale"]
    assert merge_signature(live, source).render() == "(fmt: float) -> tuple[str, int]"


INIT = textwrap.dedent('''\
    static PyObject *Err;
    PyMODINIT_FUNC PyInit__ext(void) {
        PyObject *m = PyModule_Create(&def);
        Err = PyErr_NewException("pkg._ext.Error", PyExc_ValueError, NULL);
        PyModule_AddObjectRef(m, "Error", Err);
        PyModule_AddIntConstant(m, "LEVEL", 3);
        PyModule_AddStringConstant(m, "NAME", "x");
        PyObject *d = PyDict_New();
        PyModule_AddObjectRef(m, "TABLE", d);
        return m;
    }
''')


def test_module_attributes_from_init():
    found = read_c_source(INIT)
    assert found.constants == {"LEVEL": "int", "NAME": "str", "TABLE": "dict"}
    assert found.exceptions == {"Error": "ValueError"}


def test_stub_from_c_sources_when_import_fails(tmp_path):
    from stubpy import Config, render

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    built = pkg / "_ext.cp399-win_amd64.pyd"
    built.write_bytes(b"not a module")
    (pkg / "_ext.c").write_text(GNU_STYLE + INIT, encoding="utf-8")
    for cfg in (Config(), Config(imports="none")):
        result = render(built, config=cfg)
        assert result.ok, result.diagnostics
        assert "def scale(arg: float, /) -> float: ..." in result.text
        assert "class Error(ValueError):" in result.text
        assert "LEVEL: int" in result.text
        assert any("C sources" in d.message for d in result.diagnostics)


def test_capsules_and_helper_returns():
    src = textwrap.dedent('''\
        static PyObject *wrap(void *h) { if (!h) return NULL; return PyCapsule_New(h, "x", NULL); }
        static PyObject *
        py_open(PyObject *self, PyObject *arg)
        {
            void *h = PyCapsule_GetPointer(arg, "x");
            return wrap(h);
        }
        PyMethodDef m[] = {{"open", py_open, METH_O, NULL}, {NULL}};
    ''')
    sig = read_c_source(src).signatures["open"]
    assert sig.render() == "(arg: typing_extensions.CapsuleType, /) -> typing_extensions.CapsuleType"
