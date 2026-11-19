stubpy
======

**stubpy** generates ``.pyi`` stub files for Python modules and packages. It
traces ``**kwargs`` and ``*args`` back to the parameters they forward to, so
the stub lists the real signature instead of ``**kwargs``. It uses only the
standard library.

.. rubric:: In 30 seconds

Given this module:

.. code-block:: python

   # shapes.py
   class Shape:
       def __init__(self, color: str = "black", opacity: float = 1.0): ...


   class Rect(Shape):
       def __init__(self, width: float, height: float, **kwargs):
           super().__init__(**kwargs)

From the command line:

.. code-block:: console

   $ pip install stubpy
   $ stubpy render shapes.py

From Python:

.. code-block:: python

   import stubpy

   print(stubpy.render("shapes.py").text)

Both print the stub, with ``Rect.__init__`` expanded:

.. code-block:: python

   class Shape:
       def __init__(self, color: str = 'black', opacity: float = 1.0) -> None: ...

   class Rect(Shape):
       def __init__(
           self,
           width: float,
           height: float,
           *,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...

.. rubric:: Features

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - Feature
     - What it does
     - Example
   * - ``*args`` / ``**kwargs`` back-tracing
     - Expands ``*args`` and ``**kwargs`` into the parameters of the callee, through the MRO,
       ``cls(...)``, ``self.method(...)``, plain function calls and wrappers, and drops
       parameters the call already binds.
     - ``draw(*args, **kwargs)`` becomes ``draw(x, y, *, color)``; see :doc:`guides/forwarding`
   * - Source and runtime
     - Parses the source and imports the module, using whichever says more; an import policy
       limits what may be imported, down to nothing.
     - ``stubpy render mod.py --imports none``
   * - Alias preservation
     - Keeps ``types.Length`` as written instead of expanding it to ``str | float | int``.
     - :doc:`guides/modes`
   * - Special classes
     - Dataclass, ``Enum``, ``TypedDict``, ``NamedTuple``, ``Generic``, ``TypeVar`` and
       ``@overload`` get dedicated stubs.
     - ``@overload`` variants are kept, the implementation is dropped
   * - Package generation
     - Stubs a whole tree, mirrors its layout under a stub root and adds ``__init__.pyi``.
     - ``stubpy src/mypkg -o stubs``
   * - Check mode
     - Fails when the stubs on disk differ from what would be generated; ``--diff`` shows how.
     - ``stubpy check --diff``
   * - Hints
     - ``stubpy.hint`` decorators set the signature or return type that introspection cannot
       see, or leave a symbol out.
     - ``@hint.returns("list[int]")``
   * - Incremental merge
     - Replaces only the marked region of an existing stub and keeps your edits.
     - ``stubpy --incremental``
   * - Configuration
     - ``[tool.stubpy]`` in ``pyproject.toml`` or ``stubpy.toml``; flags override the file.
     - :doc:`guides/configuration`
   * - Extension points
     - Register handlers that render your own annotation types.
     - :doc:`guides/extending`

Why stubpy
----------

``*args`` / ``**kwargs`` back-tracing
   Other generators leave ``*args`` and ``**kwargs`` as written. stubpy follows the
   forwarding call and lists the parameters the callee accepts, so editors can complete them.

Source and runtime together
   The source is always parsed; the module is also imported unless the import policy
   forbids it (``--imports none``, or ``--no-import``).
   The live objects give inherited methods and evaluated types, the source gives aliases,
   defaults and decorators as written, and the two are merged per symbol. If an import
   fails, that module is stubbed from the source with a warning.

Zero dependencies, many runtimes
   The package depends on nothing but the standard library. Supported runtimes, all tested in
   CI: CPython 3.10 to 3.15, free-threaded CPython 3.14t, PyPy 3.11, GraalPy 25 and Pyodide
   (WebAssembly). See :doc:`start/installation`.

Alias preservation
   An alias such as ``types.Length`` stays ``types.Length`` in the stub, so the
   stub reads like the source.

CI check mode
   ``stubpy check`` writes nothing and exits ``1`` when a stub is missing or stale. A
   pre-commit hook and a GitHub Actions step are in :doc:`guides/ci`.

.. toctree::
   :hidden:
   :caption: Start

   start/installation
   start/quickstart

.. toctree::
   :hidden:
   :caption: Guides

   guides/cli
   guides/configuration
   guides/modes
   guides/forwarding
   guides/hints
   guides/incremental
   guides/ci
   guides/compiled
   guides/extending

.. toctree::
   :hidden:
   :caption: API Reference

   reference/api/index
   reference/exit-codes

.. toctree::
   :hidden:
   :caption: Explanation

   explanation/architecture
   explanation/comparison

.. toctree::
   :hidden:
   :caption: Project

   contributing
   GitHub <https://github.com/wzjoriv/stubpy>
