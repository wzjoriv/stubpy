Configuration
=============

stubpy reads its options from, in order of precedence:

1. command-line flags,
2. the nearest ``stubpy.toml``, or a ``[tool.stubpy]`` table in the nearest ``pyproject.toml``,
3. the defaults.

The search starts at the first existing target (or the working folder) and walks upward.
In one folder ``stubpy.toml`` wins over ``pyproject.toml``. ``--no-config`` skips the search.

.. code-block:: toml

   # pyproject.toml
   [tool.stubpy]
   targets    = ["src/mypkg"]      # what `stubpy` and `stubpy check` act on with no paths
   modules    = ["mypkg._native"]  # importable modules to stub by name
   output_dir = "stubs"            # stub root
   mode       = "auto"
   exclude    = ["**/_vendor/*"]

In ``stubpy.toml`` the keys are top-level; there is no ``[tool.stubpy]`` header.

.. code-block:: toml

   # stubpy.toml
   targets    = ["src/mypkg"]
   output_dir = "stubs"

Keys are the field names of :class:`~stubpy.Config`; dashes are accepted
(``include-private``). An unknown key is an error with the closest valid name:

.. code-block:: text

   stubpy.toml: Unknown stubpy option 'incldue_private'; did you mean 'include_private'?

Relative ``targets`` and ``output_dir`` resolve against the folder that holds the file, not
the working directory. On Python 3.10 without ``tomli`` a small built-in parser reads the
subset stubpy needs (sections, strings, booleans, string arrays, comments).

Keys
----

.. list-table::
   :header-rows: 1
   :widths: 15 18 10 40 17

   * - Key
     - Type
     - Default
     - Description
     - CLI
   * - ``mode``
     - ``"runtime"``, ``"ast"`` or ``"auto"``
     - ``"runtime"``
     - ``runtime`` imports the module and introspects live objects, ``ast`` only parses the source, ``auto`` imports and falls back to ``ast`` when the import fails.
     - ``--mode``
   * - ``include_private``
     - ``bool``
     - ``false``
     - Stub names that start with ``_``.
     - ``--include-private``
   * - ``respect_all``
     - ``bool``
     - ``true``
     - When a module defines ``__all__``, stub only the public names it lists.
     - ``--no-respect-all``
   * - ``include_docstrings``
     - ``bool``
     - ``false``
     - Use each symbol's docstring as its stub body instead of ``...``.
     - ``--include-docstrings``
   * - ``infer_types``
     - ``bool``
     - ``false``
     - Fill in missing parameter and return types from NumPy, Google or Sphinx docstrings.
     - ``--infer-types``
   * - ``incremental``
     - ``bool``
     - ``false``
     - Wrap the stub in ``# stubpy: auto-generated`` markers and merge it into an existing ``.pyi``, keeping edits outside the markers.
     - ``--incremental``
   * - ``resolve_kwargs``
     - ``bool``
     - ``true``
     - Expand ``**kwargs`` into the parameters it is forwarded to.
     - ``--no-resolve-kwargs``
   * - ``resolve_args``
     - ``bool``
     - ``true``
     - Expand ``*args`` into the positional parameters it is forwarded to.
     - ``--no-resolve-args``
   * - ``union_style``
     - ``"modern"`` or ``"legacy"``
     - ``"modern"``
     - ``modern`` writes ``X | None``; ``legacy`` writes ``Optional[X]`` and ``Union[X, Y]``.
     - ``--union-style``
   * - ``alias_style``
     - ``"compatible"``, ``"pep695"`` or ``"auto"``
     - ``"compatible"``
     - ``compatible`` writes ``X: TypeAlias = ...``; ``pep695`` writes ``type X = ...``; ``auto`` picks ``pep695`` on Python 3.12+.
     - ``--alias-style``
   * - ``exclude``
     - list of ``str``
     - ``[]``
     - Glob patterns, relative to a folder target, of files to skip. On the command line the patterns are appended to the file's.
     - ``--exclude`` (repeatable)
   * - ``output_dir``
     - ``str`` or ``None``
     - ``None``
     - Stub root used when no output is given. Without it each stub is written next to its source.
     - ``-o`` / ``--output``
   * - ``targets``
     - list of ``str``
     - ``[]``
     - Files, folders or globs to act on when none are given.
     - positional ``TARGET``
   * - ``modules``
     - list of ``str``
     - ``[]``
     - Dotted module names to act on when none are given.
     - positional ``TARGET``
   * - ``verbose``
     - ``bool``
     - ``false``
     - Report INFO diagnostics on the command line.
     - ``--verbose``
   * - ``strict``
     - ``bool``
     - ``false``
     - Count WARNING diagnostics as failures (exit code 1).
     - ``--strict``

Booleans must be real booleans (``true``), not strings. A single string is accepted where a
list is expected (``targets = "src/mypkg"``).

From Python
-----------

:class:`~stubpy.Config` is a frozen dataclass; every field has a default.

.. code-block:: python

   import stubpy
   from stubpy import Config

   cfg = Config(mode="ast", include_private=True)       # strings coerce to the enums
   cfg2 = cfg.replace(union_style="legacy")              # a validated copy
   cfg3 = Config.from_dict({"include-private": True})    # a [tool.stubpy] table

   stubpy.generate("src/mypkg", config=cfg)
   stubpy.generate(config=stubpy.load_config())          # targets from the file

A bad value raises ``ValueError`` (unknown enum value or key) or ``TypeError`` (wrong type),
naming the allowed values.

Style options
-------------

``union_style`` and ``alias_style`` change how unions and alias declarations are written, in
every mode.

.. code-block:: python

   # aliases.py
   from typing import TypeAlias, Optional, Union

   Length: TypeAlias = str | float | int

   class Box:
       def __init__(self, w: Length, h: Optional[Length] = None, tag: Union[str, None] = None): ...

``stubpy render aliases.py`` (the defaults):

.. code-block:: python

   from __future__ import annotations
   from typing import TypeAlias

   Length: TypeAlias = str | float | int

   class Box:
       def __init__(
           self,
           w: Length,
           h: Length | None = None,
           tag: str | None = None,
       ) -> None: ...

``stubpy render aliases.py --union-style legacy --alias-style pep695``:

.. code-block:: python

   from __future__ import annotations
   from typing import Optional, Union

   type Length = Union[str, float, int]

   class Box:
       def __init__(
           self,
           w: Length,
           h: Optional[Length] = None,
           tag: Optional[str] = None,
       ) -> None: ...

.. note::

   Annotations that name an alias (``Length``, ``types.Length``) keep the alias name in every
   mode; the style applies to the alias declaration itself. See :doc:`modes`.
