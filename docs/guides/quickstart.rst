.. _quickstart:

Quickstart
==========

Single file
-----------

The simplest usage is to point stubpy at a ``.py`` file.  The stub is
written next to the source by default:

.. code-block:: bash

   stubpy path/to/mymodule.py
   # → writes path/to/mymodule.pyi

To specify a custom output path:

.. code-block:: bash

   stubpy path/to/mymodule.py -o stubs/mymodule.pyi

To also print the generated stub to stdout:

.. code-block:: bash

   stubpy path/to/mymodule.py --print

Whole package
-------------

Pass a directory to process every ``.py`` file recursively.  The
directory structure is mirrored under the output directory and every
sub-package gets an ``__init__.pyi``:

.. code-block:: bash

   stubpy mypackage/
   stubpy mypackage/ -o stubs/

Useful flags:

.. code-block:: bash

   stubpy mypackage/ --include-private   # include _private symbols
   stubpy mypackage/ --verbose           # print all diagnostics to stderr
   stubpy mypackage/ --strict            # exit 1 if any ERROR recorded
   stubpy mypackage/ --typing-style legacy   # emit Optional[X] instead of X | None
   stubpy mypackage/ --execution-mode ast_only  # no module execution

Full CLI reference:

.. code-block:: text

   usage: stubpy [-h] [-o PATH] [--print] [--include-private] [--verbose]
                 [--strict] [--typing-style {modern,legacy}]
                 [--execution-mode {runtime,ast_only,auto}] [--no-config]
                 path

   positional arguments:
     path          Python source file (.py) or package directory

   optional arguments:
     -o PATH               Output path (file) or directory (package)
     --print               Print stub to stdout (file mode only)
     --include-private     Include symbols starting with _
     --verbose             Print all diagnostics to stderr
     --strict              Exit 1 on any ERROR diagnostic
     --typing-style STYLE  modern (X | None) or legacy (Optional[X])
     --execution-mode MODE runtime | ast_only | auto
     --no-config           Ignore stubpy.toml / pyproject.toml

Configuration file
------------------

Place a ``stubpy.toml`` in the project root (or add a ``[tool.stubpy]``
section to ``pyproject.toml``) and stubpy will pick it up automatically:

.. code-block:: toml

    # stubpy.toml
    include_private = false
    typing_style    = "modern"
    output_dir      = "stubs"
    exclude         = ["**/test_*.py"]

CLI flags always override config file values.  See :ref:`api_config` for
the full list of supported keys.

Python API
----------

.. code-block:: python

   from stubpy import generate_stub, generate_package

   # Single file
   content = generate_stub("path/to/mymodule.py")
   content = generate_stub("path/to/mymodule.py", "out/mymodule.pyi")

   # Entire package
   result = generate_package("mypackage/", "stubs/")
   print(result.summary())   # "Generated 12 stubs, 0 failed."

Custom configuration
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from stubpy import generate_stub, generate_package, StubContext, StubConfig

   cfg = StubConfig(
       include_private=True,
       typing_style="legacy",    # emit Optional[X] instead of X | None
   )
   content = generate_stub("mymodule.py", ctx=StubContext(config=cfg))

   # Package with per-file context factory and exclude patterns
   cfg = StubConfig(exclude=["**/migrations/*.py"])
   result = generate_package("myapp/", "stubs/", config=cfg)

Load config from file
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from stubpy import generate_package, load_config

   cfg = load_config(".")   # finds stubpy.toml or pyproject.toml upward
   result = generate_package("mypackage/", config=cfg)

A complete example
------------------

Given this source file ``shapes.py``:

.. code-block:: python

   from typing import TypeVar, Generic, overload

   T = TypeVar("T")

   class Shape:
       def __init__(self, color: str = "black", opacity: float = 1.0) -> None:
           self.color   = color
           self.opacity = opacity

   class Circle(Shape):
       def __init__(self, radius: float, **kwargs) -> None:
           super().__init__(**kwargs)
           self.radius = radius

       @classmethod
       def unit(cls, **kwargs) -> "Circle":
           return cls(radius=1.0, **kwargs)

   class Box(Generic[T]):
       def put(self, item: T) -> None: ...
       def get(self) -> T: ...

   @overload
   def parse(x: int) -> int: ...
   @overload
   def parse(x: str) -> str: ...
   def parse(x): return x

Running:

.. code-block:: bash

   stubpy shapes.py --print

Produces:

.. code-block:: python

   from __future__ import annotations
   from typing import Generic, TypeVar, overload

   T = TypeVar('T')

   class Shape:
       def __init__(
           self,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...

   class Circle(Shape):
       def __init__(
           self,
           radius: float,
           color: str = 'black',
           opacity: float = 1.0,
       ) -> None: ...
       @classmethod
       def unit(cls, color: str = 'black', opacity: float = 1.0) -> Circle: ...

   class Box(Generic[T]):
       def put(self, item: T) -> None: ...
       def get(self) -> T: ...

   @overload
   def parse(x: int) -> int: ...

   @overload
   def parse(x: str) -> str: ...

Notice that:

- ``**kwargs`` in ``Circle.__init__`` is **resolved** to ``color`` and
  ``opacity`` from ``Shape.__init__``.
- ``Circle.unit`` excludes ``radius`` (hardcoded) and resolves the rest.
- ``Generic[T]`` is preserved using ``__orig_bases__`` (not flattened).
- Each ``@overload`` variant gets its own stub; the implementation is suppressed.
