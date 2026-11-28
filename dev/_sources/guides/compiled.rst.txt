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
  or built for another Python) is stubbed from its same-stem ``.pyx`` when there is one, else
  from its C sources (both in :doc:`compiled-sources`), else skipped with a WARNING. Named
  directly without either, it is an ERROR.
* When a ``.py`` and an extension share a name, the ``.py`` wins.
* A hand-written ``.pyi`` next to an extension is kept when generating in place (INFO
  note). Writing to an output folder, or ``--incremental``, replaces or merges it.

Submodules inside one extension
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A binding can put several modules in one file: pybind11 ``m.def_submodule("fft")`` makes
``mypkg.fft`` a module object stored as an attribute of the ``mypkg`` extension, not a
package that ``import mypkg.fft`` finds. stubpy stubs every attribute whose ``__name__`` is
``<extension>.<attribute>`` as its own module, in a stub package:

.. code-block:: text

   mypkg/__init__.pyi      # the extension's own members, plus "from . import fft as fft"
   mypkg/fft.pyi
   mypkg/linalg/__init__.pyi
   mypkg/linalg/sparse.pyi # a submodule of a submodule

A dotted name reaches one submodule and the ones below it:

.. code-block:: bash

   stubpy generate -m mypkg.fft -o stubs   # stubs/mypkg/fft.pyi
   stubpy render mypkg.fft

Module objects under other names (an imported ``numpy`` kept as an attribute) are left
out. With a single ``.pyi`` as the output, only the extension's own stub is written.

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
       Without either, the extension's C sources (see :doc:`compiled-sources`).
   * - numba
     - The Python function behind the dispatcher (``py_func``), with its annotations.

A return type none of these state is read last from the docstring: ``:rtype:``, the first line of a
``Returns`` section (``int: count``, ``list of paths``) or a leading ``Returns a list`` sentence. A
pybind11 or nanobind class with no ``py::init`` / ``nb::init`` gets no ``__init__``; protocol dunders
without a signature (``__next__``, ``__getitem__``) get their fixed parameters.

Anything without a usable signature becomes ``def name(*args: Any, **kwargs: Any) -> Any``
with an INFO diagnostic; :doc:`hints` can supply the real one.

What the stubs contain
----------------------

* Several signatures become ``@overload`` variants, constructors included.
* Protocol dunders without types get their fixed ones; see :ref:`protocol-dunders`.
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

nanobind array metadata
~~~~~~~~~~~~~~~~~~~~~~~

nanobind writes ``ndarray[dtype=float32, shape=(*, 3), order='C', device='cpu']`` in its
signatures. By default stubpy keeps only the dtype (``NDArray[numpy.float32]``). With
``array_metadata = true`` (``--array-metadata``) it writes the form nanobind's own stub
generator uses, with ``from typing import Annotated`` imported:

.. code-block:: python

   dst: Annotated[numpy.typing.NDArray[numpy.float32], dict(shape=(None, 3), order='C', device='cpu')]

Only the keys present in the signature text are written, in the order ``shape``, ``order``,
``device``; ``*`` dimensions become ``None``. An array with a dtype alone stays a plain
``NDArray``.

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

Hand-written stubs
------------------

Projects that maintain their own ``.pyi`` for a compiled module can keep it in step with the
compiled code:

.. code-block:: bash

   stubpy docstrings sync pkg/_native.pyi      # write the runtime docstrings into the stub
   stubpy docstrings list                      # which stubs would be touched
   stubpy docstrings check                     # exit 1 when a docstring is out of date (CI)
   stubpy docstrings verify                    # exit 1 when names or parameters differ (CI)

.. code-block:: python

   stubpy.sync_docstrings("pkg/_native.pyi")

``sync`` changes only the docstrings of top-level functions, classes and their methods, so
editors show the same help as ``help()``; every other byte of the stub is kept. A docstring
already in the stub is replaced. A one-line definition (``def f() -> int: return 1``) is split
so the docstring opens its body; a lone ``...`` or ``pass`` body is replaced by the docstring.

``verify`` reports what the stub and the module disagree on:

.. code-block:: text

   differs pkg/_native.pyi:
       missing from stub: mat3
       missing from stub: Box.grow
       not in module: gone
       make: stub (size), module (size, fill)

Public names and class members are compared both ways; type aliases and imports in the stub
are not counted. Parameter names are compared where the module states them: a
``__text_signature__`` or the C sources. Positional-only parameters match any name.

With no STUB and no ``-m``, the stubs come from the ``[tool.stubpy.docstrings]`` table (see
:doc:`configuration`). ``--no-config`` ignores it.

Exit codes: ``0`` up to date or synced, ``1`` out of date (``check``) or differing
(``verify``), ``2`` usage error or a module that cannot be imported or parsed. Every import or
parse failure, whatever the exception, is reported before exiting.

Limits
------

* A C function without a ``name(...) -> R`` docstring line, ``.pyx`` or sibling stub has no
  return type.
* A getset descriptor whose docstring names no type, with no sibling stub, stays ``Any``.
* A docstring-only enum default (``<Mode.FAST: 0>``) whose enum the module does not contain
  stays ``...``.
* Built-in modules with no file on disk cannot be targets.
