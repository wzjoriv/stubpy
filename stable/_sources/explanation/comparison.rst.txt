Comparison with other tools
===========================

All of these write ``.pyi`` files. They differ in what they read and what they are good at.
Check each tool's current documentation before relying on a detail here.

.. list-table::
   :header-rows: 1
   :widths: 16 21 21 21 21

   * -
     - stubpy
     - mypy ``stubgen``
     - ``pyright --createstubs``
     - pybind11-stubgen / nanobind ``stubgen``
   * - Reads
     - Source and imported modules; source only with ``--imports none``
     - Source (AST) or imported modules; C modules by introspection
     - Source, with Pyright's type inference
     - Compiled extension modules
   * - Best for
     - Pure-Python packages that forward ``**kwargs``
     - A quick stub of any package or module; the mypy ecosystem
     - A first stub from inference when a library ships none
     - Exact signatures of pybind11 or nanobind bindings
   * - ``**kwargs`` / ``*args``
     - Expanded into the callee's parameters
     - Kept as written
     - Kept as written
     - Taken from the binding's signature
   * - Types
     - From annotations, literals and optionally docstrings; no inference engine
     - Annotations; unannotated names become ``Incomplete``
     - Inferred where it can
     - From the binding's signature text
   * - Overloads, dataclass, Enum, TypedDict
     - Supported
     - Supported
     - Supported
     - Overloads and enums from the binding
   * - Hand edits survive regeneration
     - ``--incremental`` markers
     - No
     - No
     - No
   * - CI check mode
     - ``stubpy check``, exit code, ``--diff``
     - Re-run and diff yourself
     - Re-run and diff yourself
     - Re-run and diff yourself
   * - Configuration
     - ``[tool.stubpy]``
     - Command-line flags and mypy config
     - Command-line flags and Pyright config
     - Command-line flags
   * - Dependencies
     - None
     - mypy
     - Node-based Pyright
     - pybind11 / nanobind and a built module
   * - Compiled modules
     - C API, Cython, pybind11, nanobind: overloads, enums, properties, numpy types
     - Basic, from docstrings
     - Limited
     - Their main purpose

Where stubpy is stronger
------------------------

* Forwarded ``**kwargs`` and ``*args`` become real parameters, through inheritance, ``cls()``,
  ``self.method()`` and function calls.
* The live module supplies inherited and wrapped callables; the source supplies aliases,
  defaults, decorators and branches as written. ``--imports none`` runs without importing, and ``stdlib`` or a list limits what may be imported.
* ``check`` is a first-class command with a diff and exit codes, and a pre-commit hook exists.
* It has no dependencies.

Where the others are stronger
-----------------------------

* **Compiled extensions.** The pybind11 and nanobind generators read their own bindings
  exactly. stubpy also stubs compiled modules (C API, Cython, pybind11, nanobind), from
  their signatures, docstrings and any hand-written stubs beside them, but a binding's own
  tool sees types the module does not expose.
* **Inference.** Pyright can infer types where nothing is annotated. stubpy writes what the
  source and runtime show, plus literal defaults, safe return types and optional docstring
  types (see :doc:`../guides/inference`).
* **Maturity.** ``stubgen`` has years of use across large codebases. stubpy is newer; each
  release is checked against about sixty large packages (numpy, pandas, scipy, django,
  sqlalchemy, polars and others), with and without importing them, and the stubs are
  type-checked with mypy.

They also combine: generate stubs for compiled modules with the binding's own tool, and
generate the Python side with stubpy.
