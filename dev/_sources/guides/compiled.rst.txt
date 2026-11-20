Compiled modules
================

stubpy stubs compiled extension modules (``.pyd`` / ``.so``) built with the CPython C API,
Cython, pybind11 or nanobind, and Python code that wraps or subclasses them.

Targets
-------

A compiled module can be named three ways:

.. code-block:: bash

   stubpy generate mypkg/                       # folders include their extension modules
   stubpy generate -m mypkg._native             # dotted module name
   stubpy generate mypkg/_native.cp312-win_amd64.pyd

.. code-block:: python

   stubpy.generate("mypkg._native", "stubs")

* In a folder, an extension that cannot be imported on the running interpreter (not built,
  or built for another Python) is stubbed from its same-stem ``.pyx`` when there is one (see
  `Cython sources`_), else skipped with a WARNING. Named directly, it is an ERROR.
* When a ``.py`` and an extension share a name, the ``.py`` wins.
* A hand-written ``.pyi`` next to an extension is kept when generating in place (INFO
  note). Writing to an output folder, or ``--incremental``, replaces or merges it.

Where signatures come from
--------------------------

Compiled callables rarely have a Python signature, so stubpy reads what each binding tool
leaves behind, best source first:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Tool
     - Source
   * - nanobind
     - ``__nb_signature__``: exact signatures for every overload, with defaults.
   * - pybind11
     - The leading docstring lines: ``name(a: T = d) -> R``, or the numbered list after
       ``Overloaded function.``
   * - Cython
     - ``embedsignature`` docstring lines (C types mapped: ``double`` → ``float``,
       ``bint`` → ``bool``, typed memoryviews → ``Buffer``); with ``binding=True``,
       ``inspect.signature`` for names and defaults.
   * - CPython C API
     - ``__text_signature__`` (``name($module, a, /)`` docstrings), else a first docstring
       line such as ``cross(a, b) -> Vec3``. When ``inspect`` gives the parameters and the
       first docstring line names the same ones with ``-> R``, ``R`` is the return type (also
       for Cython ``binding=True`` without ``embedsignature``).
       Without either, the extension's C sources (see `C API sources`_).
   * - numba
     - The Python function behind the dispatcher (``py_func``), with its annotations.

Anything without a usable signature becomes ``def name(*args: Any, **kwargs: Any) -> Any``
with an INFO diagnostic; :doc:`hints` can supply the real one.

What the stubs contain
----------------------

* Several signatures become ``@overload`` variants, constructors included.
* pybind11 / nanobind enums become classes with their members; an enum default
  (``<Mode.FAST: 0>``) is written ``Mode.FAST`` when the enum is in scope, else ``...``.
* Properties are read-only unless the binding exposes a setter. Getset and member
  descriptors (C API, Cython) take their type from the descriptor's docstring when it states
  one (``width: float`` or ``(self) -> float``), else ``Any``.
* Types a binding does not state also come from a hand-written ``.pyi`` next to the
  extension: getset and member property types, and missing return types, when the names it
  uses can be bound.
* Enum defaults of compiled callables (``<Mode.FAST: 0>``) are qualified from the annotation
  or the live object, and the enum's module is imported.
* With ``include_docstrings`` each ``@overload`` variant carries its own docstring (the
  nanobind per-overload text, or the paragraph under ``1. name(...)`` in a pybind11
  ``Overloaded function.`` docstring).
* An enum default is also kept when the enum comes from another module whose import the
  stub already writes for an annotation.
* Fully qualified type names are shortened when they belong to the same module and keep
  their import otherwise (``numpy.typing.NDArray[numpy.float32]`` with ``import numpy``).

pybind11 class with overloaded constructors and a settable property:

.. code-block:: python

   class LightSource:
       @overload
       def __init__(self, azimuth: SupportsFloat | SupportsIndex, elevation: SupportsFloat | SupportsIndex) -> None: ...
       @overload
       def __init__(
           self,
           x: SupportsFloat | SupportsIndex,
           y: SupportsFloat | SupportsIndex,
           z: SupportsFloat | SupportsIndex,
       ) -> None: ...
       @property
       def kind(self) -> LightType: ...
       @property
       def position(self) -> Annotated[list[float], 'FixedSize(3)']: ...
       @position.setter
       def position(self, value: Annotated[Sequence[SupportsFloat | SupportsIndex], 'FixedSize(3)']) -> None: ...

nanobind enum and keyword-only arguments on numpy arrays:

.. code-block:: python

   class LineJoin(Enum):
       MITER = 0
       ROUND = 1
       BEVEL = 2

   def over(
       dst: numpy.typing.NDArray[numpy.float32],
       src: numpy.typing.NDArray[numpy.float32],
       *,
       opacity: float = 1.0,
   ) -> None: ...

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
  ``src/`` folder beside it, or in a ``src/`` folder beside its package; otherwise the file
  defining ``PyInit__x`` there, with the other C files of that folder. Cython output is ignored.
* ``PyMethodDef`` tables give the functions; tables named by a type's ``tp_methods`` (or a
  ``PyType_Slot`` ``Py_tp_methods``) give its methods, and ``tp_init`` its constructor.
* ``METH_NOARGS`` gives no parameters, ``METH_O`` one positional-only parameter named after
  the C argument. ``METH_VARARGS`` reads the ``PyArg_ParseTuple`` /
  ``PyArg_ParseTupleAndKeywords`` call: names from ``kwlist`` (or the C variables, positional
  only), ``|`` optional (default ``...``), ``$`` keyword-only, and types from the units:
  ``i`` / ``l`` / ``n`` → ``int``, ``d`` / ``f`` → ``float``, ``s`` / ``U`` → ``str``,
  ``z`` → ``str | None``, ``y`` → ``bytes``, ``p`` → ``bool``, ``(ii)`` →
  ``tuple[int, int]``, ``O!`` with ``&PyList_Type`` or a type of the module → that type,
  ``O`` → ``Any``. ``PyArg_UnpackTuple`` gives positional-only ``Any`` parameters.
* Argument Clinic ``/*[clinic input]`` blocks give full signatures: converters as types,
  ``/`` and ``*``, Python defaults, and ``-> double`` style return converters.
* Returns: ``Py_RETURN_NONE`` → ``None``, ``PyLong_From*`` → ``int``,
  ``PyFloat_FromDouble`` → ``float``, ``PyBool_FromLong`` → ``bool``, ``PyUnicode_From*``
  → ``str``, ``Py_BuildValue("(dd)")`` → ``tuple[float, float]``; when every non-error
  ``return`` agrees (``None`` plus one type gives ``T | None``). Anything else stays untyped.
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

Python code around compiled code
--------------------------------

``*args`` / ``**kwargs`` back-tracing (:doc:`forwarding`) continues into compiled callables. A Python
subclass whose ``__init__`` forwards ``*args, **kwargs`` to a compiled constructor gets the
compiled parameters:

.. code-block:: python

   # raster.py
   class Rasterizer(_scanline.Rasterizer):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)

.. code-block:: python

   class Rasterizer(_scanline.Rasterizer):
       def __init__(self, width: int, height: int, *, rule: str = 'nonzero', samples: int = 4) -> None: ...

When the compiled constructor has several overloads and the subclass's ``__init__`` only
passes ``*args, **kwargs`` on unchanged, every overload is copied as an ``@overload``
variant of the subclass's ``__init__``:

.. code-block:: python

   class Transfer(TransferFunction):
       @overload
       def __init__(self) -> None: ...
       @overload
       def __init__(self, kind: TransferType, values: Sequence[SupportsFloat | SupportsIndex]) -> None: ...
       @overload
       def __init__(self, slope: SupportsFloat | SupportsIndex, intercept: SupportsFloat | SupportsIndex = 0.0) -> None: ...

When the subclass adds or binds parameters of its own, it keeps ``*args, **kwargs`` and an
INFO diagnostic says so: one caller overload per callee overload, each rebinding the
caller's parameters, would too easily be wrong.

Docstrings for hand-written stubs
---------------------------------

Projects that maintain their own ``.pyi`` for a compiled module can keep its docstrings in
step with the compiled code, so editors show the same help as ``help()``:

.. code-block:: bash

   stubpy docstrings sync pkg/_native.pyi      # write the runtime docstrings into the stub
   stubpy docstrings list                      # which stubs would be touched
   stubpy docstrings check                     # exit 1 when a stub is out of date (CI)

.. code-block:: python

   stubpy.sync_docstrings("pkg/_native.pyi")

Only docstrings of top-level functions, classes and their methods change; every other byte
of the stub is kept. A docstring already in the stub is replaced. A one-line definition
(``def f() -> int: return 1``) is split so the docstring opens its body; a lone ``...`` or
``pass`` body is replaced by the docstring.

With no STUB and no ``-m``, the stubs come from the config file:

.. code-block:: toml

   [tool.stubpy.docstrings]
   packages    = ["mypkg"]    # folders searched for *.pyx / compiled modules with a same-stem .pyi beside them
   import_root = "src"        # module names are relative to it; default: found by walking up __init__.py folders
   overrides   = {"mypkg.core" = "stubs/core.pyi", "mypkg._old" = ""}

Paths are relative to the config file. ``overrides`` maps a module to a stub path; an empty
string drops a discovered module. In Python, use ``stubpy.Config(docstrings={...})``.
``--no-config`` ignores the table.

Exit codes: ``0`` up to date or synced, ``1`` out of date (``check``), ``2`` usage error or a
module that cannot be imported or parsed. Every import or parse failure, whatever the
exception, is reported before exiting. Compiled modules need the import, so they cannot be
stubbed with ``--imports none`` (or ``--no-import``) when they have no ``.pyx`` beside them:
named directly that is an ERROR, found in a folder it is a WARNING and no stub.

Limits
------

* A C function without a ``name(...) -> R`` docstring line, ``.pyx`` or sibling stub has no
  return type.
* A getset descriptor whose docstring names no type, with no sibling stub, stays ``Any``.
* A docstring-only enum default (``<Mode.FAST: 0>``) whose annotation does not name the enum
  stays ``...``.
* Built-in modules with no file on disk cannot be targets.
