Modes
=====

``mode`` decides whether stubpy imports your code.

.. list-table::
   :header-rows: 1
   :widths: 12 50 38

   * - Mode
     - What it does
     - Use when
   * - ``runtime``
     - Imports the module and introspects the live objects. The default.
     - The module imports cleanly in the current environment.
   * - ``ast``
     - Parses the source and never executes it.
     - The import has side effects, needs unavailable dependencies, or you only
       have source.
   * - ``auto``
     - Tries ``runtime``; if the import fails, falls back to ``ast``.
     - A package where only some modules are hard to import.

.. code-block:: console

   $ stubpy src/mypkg --mode auto

.. code-block:: python

   stubpy.render("mod.py", config=stubpy.Config(mode="ast"))

What each mode sees
-------------------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Aspect
     - ``runtime``
     - ``ast``
   * - Inherited methods and bases from other modules
     - Resolved from the live classes; ``**kwargs`` is traced through the MRO.
     - Only what the source shows.
   * - Default values
     - The evaluated value (``os.sep`` becomes ``'\\'`` on Windows).
     - The expression as written (``os.sep``).
   * - Return type of ``__init__``
     - Added (``-> None``).
     - Not added.
   * - Decorated or wrapped callables
     - Unwrapped to the real signature.
     - The source ``def``.
   * - Aliases defined in the same module
     - Kept by name (``Length``).
     - Kept by name (``Length``).
   * - Aliases from another module (``types.Length``)
     - Kept by name.
     - Kept by name.
   * - Union and alias style options
     - Applied.
     - Applied to every annotation that parses.
   * - Import-time side effects
     - Run.
     - None.

Defaults and ``__init__`` return types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # mixed.py
   import os

   def f(x, y=os.sep, *, z: list[int] | None = None): ...

``stubpy render mixed.py`` on Windows:

.. code-block:: python

   def f(
       x,
       y: str = '\\',
       *,
       z: list[int] | None = None,
   ): ...

``stubpy render mixed.py --mode ast``:

.. code-block:: python

   import os

   def f(
       x,
       y = os.sep,
       *,
       z: list[int] | None = None,
   ): ...

Runtime defaults can differ between machines. Use ``ast`` (or a literal default) when the
stub must be the same everywhere.

Aliases
~~~~~~~

An alias imported from another module keeps its name in both modes:

.. code-block:: python

   # pk/types.py
   from typing import TypeAlias
   Length: TypeAlias = str | float | int

   # pk/box.py
   from . import types

   class Box:
       def __init__(self, w: types.Length, h: types.Length = 0): ...

``stubpy render pk/box.py``:

.. code-block:: python

   from . import types

   class Box:
       def __init__(self, w: types.Length, h: types.Length = 0) -> None: ...

Side effects and safety
-----------------------

``runtime`` executes the module's top level. Anything it does at import time happens when
you generate stubs:

.. code-block:: python

   # sidefx.py
   print("importing sidefx")

   def f(x: int) -> int:
       return x

.. code-block:: console

   $ stubpy render sidefx.py --mode ast       # nothing is printed by the module
   $ stubpy render sidefx.py                  # prints "importing sidefx" first

Use ``ast`` for untrusted code. For a package, stubpy puts the package root on ``sys.path``
for the run and restores it afterwards.

Failed imports
--------------

In ``runtime`` a module that cannot be imported gives an ERROR diagnostic, is not written, and
the run continues with the other modules (exit code ``1``). In ``auto`` the same module is
stubbed from source:

.. code-block:: python

   # broken.py
   import not_installed_pkg

   def f(x: int) -> int: ...

.. code-block:: console

   $ stubpy render broken.py
   FAILED broken.py
       [ERROR] (load) broken.py: Module execution failed: ModuleNotFoundError: No module named 'not_installed_pkg'
   $ stubpy render broken.py --mode auto
   def f(x: int) -> int: ...

Names and visibility
--------------------

These apply in every mode:

* A module that defines ``__all__`` is stubbed with only the names it lists
  (``respect_all``, on by default).
* Names that start with ``_`` are left out unless ``include_private`` is on.
* A ``# stubpy: ignore`` comment at the top of a file leaves its contents out of the stub.
* ``@hint.ignore`` leaves one function or class out; see :doc:`hints`.

.. code-block:: python

   # priv.py
   __all__ = ["a"]
   def a(): ...
   def b(): ...
   def _c(): ...

``stubpy render priv.py`` gives only ``a``. ``--no-respect-all`` adds ``b``;
``--include-private`` adds ``_c``.

Lazy module attributes
----------------------

A module ``__getattr__`` (PEP 562) that loads names on first use is read in both modes: a
mapping such as ``{"Canvas": ".core"}`` or ``{"parse": ("io.parser", "parse")}`` tested with
``if name in MAPPING:``, and ``if name == "Canvas":`` branches that import the name and
return it. In runtime mode the remaining ``__all__`` names are looked up with
``getattr(module, name)``. Each lazy name becomes a re-export (``from .core import Canvas as
Canvas``) or, for a plain value, a typed variable.

.. code-block:: python

   # pkg/__init__.py
   import importlib

   __all__ = ["Canvas", "VERSION"]
   _LAZY = {"Canvas": ".core"}

   def __getattr__(name):
       if name in _LAZY:
           return getattr(importlib.import_module(_LAZY[name], __name__), name)
       if name == "VERSION":
           return "1.0"
       raise AttributeError(name)

.. code-block:: python

   from .core import Canvas as Canvas

   __all__ = ["Canvas", "VERSION"]

   VERSION: str

``__getattr__`` itself leaves the stub when it ends by raising and every lazy name was
found. Otherwise it stays, with an INFO diagnostic naming the unresolved names.
