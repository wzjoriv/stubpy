Source and runtime
==================

stubpy has one pipeline. It always parses the source. Unless the import policy forbids it,
it also imports the module and uses the live objects wherever they say more than the source
does. The two are
merged per symbol and per parameter, so a module is never stubbed from one side alone when
the other has the better answer.

What comes from where
---------------------

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Aspect
     - Live module
     - Source
   * - Evaluated signatures and types
     - Used.
     - Fallback when the import fails.
   * - Inherited members, third-party bases
     - Resolved from the real classes.
     - Followed through imports inside the package, and into installed packages by reading
       their source (or bundled ``.pyi`` / ``<name>-stubs``) without importing them.
       Standard-library and builtin callees resolve in both modes.
   * - Compiled extension modules
     - The only source (see :doc:`compiled`).
     - Not available.
   * - ``**kwargs`` / ``*args`` forwarding
     - Traced through the live callees and MRO.
     - Traced through the harvested sources; closes a ``**kwargs`` that runtime leaves open
       when it can (see :doc:`forwarding`).
   * - Aliases (``LengthLike``)
     - Expanded to the union.
     - Kept as written, also for class attributes.
   * - Defaults that read a module attribute (``os.sep``, ``math.pi``)
     - The evaluated, platform-specific value.
     - Kept as written; the import is added.
   * - Decorators, ``sys.version_info`` / ``sys.platform`` branches
     - Only what the running interpreter took.
     - All branches and the decorators.
   * - Raw annotations, ``TYPE_CHECKING`` names
     - Resolved, or lost when the name is not importable at runtime.
     - Kept; also imported into a subclass stub in another module that inherits a parameter
       typed with one.
   * - Callables wrapped without ``functools.wraps``
     - Seen as ``(*args, **kwargs)``.
     - The real ``def`` signature is taken.

How they are merged
-------------------

The source wins wherever the live module is missing or worse. Aliases and defaults keep
their written form:

.. code-block:: python

   # mixed.py
   import math, os
   from typing import TypeAlias

   LengthLike: TypeAlias = str | float | int

   def f(x: LengthLike, y=os.sep, z=math.pi): ...

``stubpy render mixed.py`` gives the same stub on every platform:

.. code-block:: python

   import math
   import os
   from typing import TypeAlias

   LengthLike: TypeAlias = str | float | int

   def f(
       x: LengthLike,
       y: str = os.sep,
       z: float = math.pi,
   ): ...

Runtime alone would have written ``x: str | float | int`` and ``y: str = '\'`` on Windows.

A decorator without ``functools.wraps`` hides the signature from introspection:

.. code-block:: python

   # deco.py
   def logged(fn):
       def inner(*args, **kwargs):
           return fn(*args, **kwargs)
       return inner

   @logged
   def area(w: int, h: int = 1) -> int: ...

Runtime sees ``inner(*args, **kwargs)``. stubpy takes the ``def``:

.. code-block:: python

   def area(w: int, h: int = 1) -> int: ...

Annotations under ``TYPE_CHECKING`` are kept even though they do not exist at runtime:

.. code-block:: python

   # pk/base.py
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from .shapes import Shape

   class Base:
       def __init__(self, shape: "Shape"): ...

   # pk/box.py
   from .base import Base

   class Box(Base):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)

``stubpy render pk/box.py`` imports ``Shape`` into the ``Box`` stub and keeps
``shape: Shape`` in its signature.

Import policy
-------------

Which modules stubpy may import is set by ``imports`` and ``deny_imports``:

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - ``imports``
     - Meaning
   * - ``"all"`` (default)
     - Any module may be imported.
   * - ``"stdlib"``
     - Only the standard library.
   * - ``"none"``
     - Nothing is imported or executed; the stub comes from the source alone.
   * - a list, ``["mypkg", "numpy"]``
     - The standard library plus those names.

``deny_imports`` lists names that are never imported, whatever ``imports`` says; deny wins
over allow. A name is a dotted module name: ``pkg`` covers ``pkg`` and its submodules, and
``pkg.*`` means the same. The parents of an allowed name are allowed too, since importing
``pkg.sub`` needs ``pkg``.

.. code-block:: toml

   [tool.stubpy]
   imports      = ["mypkg"]        # the standard library and mypkg, nothing third-party
   deny_imports = ["mypkg.gui"]

.. code-block:: console

   $ stubpy src/mypkg --imports none
   $ stubpy src/mypkg --imports stdlib --allow-import mypkg --deny-import mypkg.gui

``--imports {all,none,stdlib}`` sets the mode, ``--allow-import NAME`` (repeatable) adds to the
list form, ``--deny-import NAME`` (repeatable) adds to ``deny_imports``, and ``--no-import``
is the same as ``--imports none``. From Python:

.. code-block:: python

   stubpy.render("mod.py", config=stubpy.Config(imports="none"))

:attr:`Config.may_import <stubpy.Config.may_import>` is ``False`` only for ``"none"``. The
policy is :class:`stubpy.config.ImportPolicy`.

How it is enforced
~~~~~~~~~~~~~~~~~~

While a module loads, a ``sys.meta_path`` guard refuses every module outside the policy,
whether the target imports it directly or through another import, compiled extensions
included. Modules already imported before the run are not affected. The guard is removed
afterwards. The policy covers the targets themselves: with ``"stdlib"`` your own package is
not imported either, so use ``imports = ["mypkg"]`` to import it and nothing third-party.

A target whose import is blocked, directly or through one of its imports, is stubbed from its
source, with an INFO diagnostic:

.. code-block:: text

   [INFO] (load) ext.py: Import blocked by stubpy import policy: mypkg.ext; stubbing from the source

With ``"none"`` nothing is imported at all (``imports is 'none': module execution skipped``).

.. warning::

   The policy limits import-time side effects. It is not a security sandbox: code that is
   imported can still do anything, and a module that is allowed can import what it likes
   from the allowed set. A target's own code runs until it reaches a blocked import, and
   modules already imported before the run are not affected. Do not run stubpy on untrusted
   code.

Use it for:

* applications with import-time side effects (they run when the module is imported); set
  ``imports = "none"`` or ``"stdlib"``, or a list with your own package, in ``[tool.stubpy]``,
* modules whose dependencies are not installed,
* CI that does not install the project's dependencies.

.. code-block:: python

   # sidefx.py
   print("importing sidefx")

   def f(x: int) -> int:
       return x

.. code-block:: console

   $ stubpy render sidefx.py --imports none   # nothing is printed by the module
   $ stubpy render sidefx.py                  # prints "importing sidefx" first

For a package, stubpy puts the package root on ``sys.path`` for the run and restores it
afterwards.

What a stub made without importing cannot do:

* Compiled extension modules can only be stubbed by importing them, except through a
  same-stem ``.pyx`` (see :doc:`compiled`). Named directly they are an ERROR; found in a
  folder they give a WARNING and no stub.
* Code generated at import time (classes built in a loop, ``setattr`` on the module) is not
  in the source.
* Inheritance from third-party bases is read from the installed package's source, its
  bundled ``.pyi`` or its ``<name>-stubs`` package, found without importing it; a base that
  cannot be found stops the walk. Standard-library and builtin callees (``open``,
  ``subprocess.run``, ``json.dumps``) resolve either way.
* Evaluated defaults and types give way to the expression as written.

Failed imports
--------------

When a module cannot be imported, stubpy falls back to the source for that module and records
a WARNING. The other modules are unaffected. With ``--strict`` warnings fail the run
(exit code ``1``).

.. code-block:: python

   # broken.py
   import not_installed_pkg

   def f(x: int) -> int: ...

.. code-block:: console

   $ stubpy render broken.py
   [WARNING] (load) broken.py: Import failed, falling back to source analysis: ModuleNotFoundError: No module named 'not_installed_pkg'
   def f(x: int) -> int: ...

A file that does not parse is still an ERROR and is not written.

Names and visibility
--------------------

These apply with or without the import:

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

A module ``__getattr__`` (PEP 562) that loads names on first use is read from the source: a
mapping such as ``{"Canvas": ".core"}`` or ``{"parse": ("io.parser", "parse")}`` tested with
``if name in MAPPING:``, and ``if name == "Canvas":`` branches that import the name and
return it. When the module is imported, the remaining ``__all__`` names are looked up with
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
