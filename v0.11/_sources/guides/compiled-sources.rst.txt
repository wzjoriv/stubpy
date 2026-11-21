Reading compiled sources
========================

A built extension tells ``inspect`` little: often no parameter names, no types, no return type.
When its sources sit beside it, stubpy reads them, without compiling anything, and fills in
what the runtime lacks. This page lists what is read from each kind of source; :doc:`compiled`
covers how compiled modules are stubbed overall.

Cython sources
--------------

``.pyx`` files are module files: a folder run or an explicit ``.pyx`` target stubs them.

* A built extension that imports wins and is introspected. The ``.pyx`` fills in what the
  build lacks: parameter types, defaults (enum members such as ``Table.DC``), docstrings and
  the types of ``cdef public`` / ``readonly`` fields.
* An unbuilt ``.pyx`` is stubbed from the source alone (INFO ``Stubbed from the Cython
  source; no build of it was imported``).
* An extension that cannot be imported falls back to its same-stem ``.pyx`` with a WARNING.
* The source is read with Cython's own parser (``Cython.Compiler``) when Cython is
  installed, otherwise with a built-in reader of ``def`` and ``cpdef`` signatures (multi-line
  signatures, decorators, ``nogil``, ``except`` and ``noexcept`` clauses).
* ``cdef`` functions are not visible from Python and are skipped. ``cpdef enum`` becomes an
  ``IntEnum``. C types map as for ``embedsignature``: ``double`` to ``float``, ``bint`` to
  ``bool``, typed memoryviews to ``Buffer``.
* A ``def``, ``cpdef`` or property getter without a declared return type gets one when every
  ``return`` is plain: literals, typed parameters and ``cdef`` locals, the class's ``cdef``
  fields (``self.width``), ``.shape[i]``, builtin conversions (``int(...)``, ``len(...)``),
  classes of the module and NumPy factories (``np.zeros(..., dtype=np.uint8)`` gives
  ``numpy.typing.NDArray[numpy.uint8]``). A body without a returned value gives ``None``;
  generators and anything else stay untyped.

.. code-block:: cython

   # shapes.pyx
   cpdef enum Table:
       DC = 0
       AC = 1

   cdef double _helper(double x):
       return x

   def scale(double x, int n=2, bint flip=False, *, Table table=Table.DC):
       return x * n

   cpdef double area(double w, double h=1.0) nogil:
       return w * h

   cdef class Box:
       cdef public double width
       cdef readonly int count

``stubpy render shapes.pyx``:

.. code-block:: python

   from enum import IntEnum
   from typing import Any

   class Table(IntEnum):
       DC = 0
       AC = 1

   DC: Table
   AC: Table

   class Box:
       @property
       def width(self) -> float: ...
       @width.setter
       def width(self, value: Any) -> None: ...
       @property
       def count(self) -> int: ...

   def scale(
       x: float,
       n: int = 2,
       flip: bool = False,
       *,
       table: Table = Table.DC,
   ): ...

   def area(w: float, h: float = 1.0) -> float: ...

C API sources
-------------

A C API function registered with ``METH_VARARGS`` and no signature docstring has nothing
for ``inspect`` to read. When the C sources sit next to the built module, stubpy reads them
(no compiler, no C parser) and fills what the runtime lacks; a text signature, a docstring
line, a ``.pyx`` or a sibling ``.pyi`` still wins on what it states.

* Sources: ``_x.c`` (or ``.cc`` / ``.cpp`` / ``.cxx``) beside ``_x.cp312-win_amd64.pyd``, in a
  ``src/`` folder beside it, in a ``src/`` folder beside its package, or in another folder beside
  it (``_ext/``); otherwise the file defining ``PyInit__x`` there, with the other C files of that
  folder. Cython output is ignored. Definitions with the return type on its own line are read.
* Without the built module (it fails to import, or ``--imports none``), the stub comes from the
  sources alone, with a WARNING: the functions with their method-table docstrings and the
  types below, the classes, constants added with ``PyModule_AddIntConstant`` /
  ``AddStringConstant`` / ``AddObject`` (typed from the object's constructor, such as
  ``PyDict_New``), and exceptions from ``PyErr_NewException`` with their base class.
* ``PyMethodDef`` tables give the functions; tables named by a type's ``tp_methods`` (or a
  ``PyType_Slot`` ``Py_tp_methods``) give its methods, and ``tp_init`` its constructor.
* ``METH_NOARGS`` gives no parameters.
* ``METH_O`` gives one positional-only parameter named after the C argument, typed by its first
  conversion: ``PyLong_As*`` → ``int``, ``PyFloat_AsDouble`` → ``float``,
  ``PyUnicode_AsUTF8`` → ``str``, ``PyObject_GetBuffer`` → ``Buffer``,
  ``PyCapsule_GetPointer`` → ``CapsuleType``.
* ``METH_VARARGS`` reads the ``PyArg_ParseTuple`` / ``PyArg_ParseTupleAndKeywords`` call:
  names from ``kwlist`` (or the C variables, positional only), ``|`` optional (default
  ``...``), ``$`` keyword-only, and types from the units:
  ``i`` / ``l`` / ``n`` → ``int``, ``d`` / ``f`` → ``float``, ``s`` / ``U`` → ``str``,
  ``z`` → ``str | None``, ``y`` → ``bytes``, ``p`` → ``bool``, ``(ii)`` →
  ``tuple[int, int]``, ``O!`` with ``&PyList_Type`` or a type of the module → that type,
  ``O`` → ``Any``. ``PyArg_UnpackTuple`` gives positional-only ``Any`` parameters.
* Argument Clinic ``/*[clinic input]`` blocks give full signatures: converters as types,
  ``/`` and ``*``, Python defaults, and ``-> double`` style return converters.
* A docstring signature whose names differ from the C ones keeps its names and takes these
  types by position.
* Returns: ``Py_RETURN_NONE`` → ``None``, ``PyLong_From*`` → ``int``,
  ``PyFloat_FromDouble`` → ``float``, ``PyBool_FromLong`` → ``bool``, ``PyUnicode_From*``
  → ``str``, ``PyCapsule_New`` → ``CapsuleType``, ``Py_BuildValue("(dd)")`` →
  ``tuple[float, float]``, and ``return helper(...)`` the helper's own return type; when every
  non-error ``return`` agrees (``None`` plus one type gives ``T | None``). Anything else stays
  untyped.
* ``PyGetSetDef`` getters take the getter's return type; ``PyMemberDef`` ``T_INT`` /
  ``T_DOUBLE`` / ``T_BOOL`` / ``T_STRING`` / ``T_OBJECT`` give ``int`` / ``float`` /
  ``bool`` / ``str`` / ``Any``.
* Comments and preprocessor lines are dropped (both ``#if`` branches are read); rows, calls
  and format strings that do not have the expected shape are skipped, as are
  ``METH_FASTCALL`` functions without a clinic block and optional groups (``[`` ``]``).

.. code-block:: c

   static PyObject *clamp(PyObject *self, PyObject *args, PyObject *kwds) {
       static char *kwlist[] = {"value", "low", "high", "strict", NULL};
       ...
       if (!PyArg_ParseTupleAndKeywords(args, kwds, "d|dd$p:clamp", kwlist, ...)) return NULL;
       return PyFloat_FromDouble(...);
   }

.. code-block:: python

   def clamp(
       value: float,
       low: float = ...,
       high: float = ...,
       *,
       strict: bool = ...,
   ) -> float: ...

When the package's ``__init__`` fails to import, the extension modules in it are still
loaded on their own, under placeholder parent packages, with a WARNING
(``...; loaded pkg.sub._ext on its own instead``).

