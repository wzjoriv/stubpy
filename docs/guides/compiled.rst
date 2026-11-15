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
  or built for another Python) is skipped with a WARNING. Named directly, it is an ERROR.
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
   * - numba
     - The Python function behind the dispatcher (``py_func``), with its annotations.

Anything without a usable signature becomes ``def name(*args: Any, **kwargs: Any) -> Any``
with an INFO diagnostic; :doc:`hints` can supply the real one.

What the stubs contain
----------------------

* Several signatures become ``@overload`` variants, constructors included.
* pybind11 / nanobind enums become classes with their members; an enum default
  (``<Mode.FAST: 0>``) is written ``Mode.FAST`` when the enum is in scope, else ``...``.
* Properties are read-only unless the binding exposes a setter.
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

Python code around compiled code
--------------------------------

``**kwargs`` back-tracing (:doc:`kwargs`) continues into compiled callables. A Python
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
   stubpy docstrings check                     # exit 1 when a stub is out of date (CI)

.. code-block:: python

   stubpy.sync_docstrings("pkg/_native.pyi")

Only docstrings of top-level functions, classes and their methods change; every other byte
of the stub is kept. Stubs are found next to their module (``pkg/_x.pyx`` or
``pkg/_x.*.pyd`` beside ``pkg/_x.pyi``). ``check`` exits 2 when a module cannot be imported.

Limits
------

* C API and Cython functions without ``embedsignature`` have no return type unless the first
  docstring line names one.
* Getset / member descriptors without a binding signature are typed ``Any``.
* Built-in modules with no file on disk cannot be targets.
