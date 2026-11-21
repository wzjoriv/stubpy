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
   imports    = ["mypkg"]          # the standard library and mypkg may be imported
   extend_exclude = ["**/_vendor/*"]

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
   * - ``imports``
     - ``"all"``, ``"none"``, ``"stdlib"`` or list of ``str``
     - ``"all"``
     - Which modules may be imported, so that the live objects can be merged with the source. ``"none"`` executes nothing; ``"stdlib"`` allows only the standard library; a list allows the standard library plus those names. A blocked or failed import falls back to the source. See :doc:`modes`.
     - ``--imports``, ``--allow-import`` (repeatable), ``--no-import``
   * - ``deny_imports``
     - list of ``str``
     - ``[]``
     - Module names that are never imported; wins over ``imports``.
     - ``--deny-import`` (repeatable)
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
     - Fill in missing parameter and return types from NumPy, Google or Sphinx docstrings. Safe
       return types and forwarded keywords are inferred without it; see :doc:`inference`.
     - ``--infer-types``
   * - ``array_metadata``
     - ``bool``
     - ``false``
     - Keep the shape, order and device of nanobind arrays as ``Annotated[NDArray[...], dict(...)]``
       instead of a plain ``NDArray``; see :doc:`compiled`.
     - ``--array-metadata``
   * - ``incremental``
     - ``bool``
     - ``false``
     - Wrap the stub in ``# stubpy: auto-generated`` markers and merge it into an existing ``.pyi``, keeping edits outside the markers.
     - ``--incremental``
   * - ``stub_package``
     - ``bool``
     - ``false``
     - Write each top-level package as a stub-only distribution ``<output>/<pkg>-stubs/``; see :doc:`stub-packages`.
     - ``--stub-package``
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
   * - ``version_branches``
     - ``"emit"`` or ``"resolve"``
     - ``"emit"``
     - ``emit`` copies ``if sys.version_info ...`` / ``if sys.platform ...`` blocks into the stub with every branch; ``resolve`` keeps only the branch the running interpreter takes.
     - ``--version-branches``
   * - ``exclude``
     - list of ``str``
     - see `What gets skipped`_
     - Patterns of files and folders a folder target skips. Setting it replaces the defaults; ``[]`` turns them all off.
     - ``--exclude`` (repeatable)
   * - ``extend_exclude``
     - list of ``str``
     - ``[]``
     - Patterns added to ``exclude`` (or to its defaults).
     - ``--extend-exclude`` (repeatable)
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
   * - ``target_python``
     - ``str``
     - ``"3.10"``
     - Oldest Python the stubs must import on. ``typing`` names added later (``Self``,
       ``override``, ``TypeIs``, ``Unpack``, ``ReadOnly``, ``deprecated`` from
       ``warnings``, ...) are imported from ``typing_extensions``; names the target has come
       from ``typing``, whatever the source or the running interpreter used.
     - ``--target-python``

Booleans must be real booleans (``true``), not strings. A single string is accepted where a
list is expected (``targets = "src/mypkg"``).

What gets skipped
-----------------

A folder target skips these by default:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Pattern
     - Skips
   * - ``.*``
     - Hidden files and folders.
   * - ``__pycache__``, ``build``, ``dist``, ``.venv``, ``venv``, ``.git``, ``.tox``, ``.nox``
     - Caches, build output, environments and tool folders.
   * - ``*.egg-info``
     - Packaging metadata folders.
   * - ``<non-identifier>``
     - Built-in rule: folders and module files whose name Python cannot import
       (``name copy.py``, ``foo-bar.py``, ``2thing.py``, backup copies).

A pattern that contains ``/`` matches the path relative to the folder target; one without
matches any single folder or file name on the path. ``exclude`` replaces the defaults, and
``extend_exclude`` adds to them:

.. code-block:: toml

   [tool.stubpy]
   extend_exclude = ["tests", "mypkg/_vendor/*"]   # on top of the defaults

   # or replace the defaults; this one keeps hidden folders in:
   # exclude = ["__pycache__", "build", "dist", ".venv", "venv", "*.egg-info",
   #            ".git", ".tox", ".nox", "<non-identifier>"]

On the command line ``--exclude`` replaces the defaults too and ``--extend-exclude`` adds to
them. A file named directly as a target is always processed, so a hidden or oddly named file
passed explicitly works as a loose script. Skipped files never count as failures in
``generate`` or ``check``.

``--show-excluded`` lists each skipped path with the pattern that matched, and ``--verbose``
prints one INFO line listing them. :attr:`Report.excluded <stubpy.Report.excluded>` holds the
``(path, pattern)`` pairs.

.. code-block:: console

   $ stubpy generate . --show-excluded
   excluded .hidden\x.py (.*)
   excluded build\y.py (build)
   excluded mypkg\core copy.py (<non-identifier>)
   excluded mypkg\foo-bar.py (<non-identifier>)
   wrote mypkg\__init__.pyi
   wrote mypkg\core.pyi
   Generated 2 stubs, 0 failed.

Docstring targets
-----------------

``stubpy docstrings`` (see :doc:`cli` and :doc:`compiled`) reads the stubs it acts on from
the ``[tool.stubpy.docstrings]`` table when it gets no STUB and no ``-m``. Paths are relative
to the config file.

.. code-block:: toml

   [tool.stubpy.docstrings]
   packages    = ["mypkg"]    # folders searched for *.pyx / compiled modules with a same-stem .pyi beside them
   import_root = "src"        # module names are relative to it; default: found by walking up __init__.py folders
   overrides   = {"mypkg.core" = "stubs/core.pyi", "mypkg._old" = ""}

``overrides`` maps a module to a stub path; an empty string drops a discovered module. In
Python the table is ``Config(docstrings={...})``, coerced to
:class:`~stubpy.config.DocstringTargets`.

From Python
-----------

:class:`~stubpy.Config` is a frozen dataclass; every field has a default.

.. code-block:: python

   import stubpy
   from stubpy import Config

   cfg = Config(imports="none", include_private=True)   # strings coerce to the enums
   cfg2 = cfg.replace(union_style="legacy")              # a validated copy
   cfg3 = Config.from_dict({"include-private": True})    # a [tool.stubpy] table

   stubpy.generate("src/mypkg", config=cfg)
   stubpy.generate(config=stubpy.load_config())          # targets from the file

A bad value raises ``ValueError`` (unknown enum value or key) or ``TypeError`` (wrong type),
naming the allowed values.

Style options
-------------

``union_style`` and ``alias_style`` change how unions and alias declarations are written, with
or without the import.

.. code-block:: python

   # aliases.py
   from typing import TypeAlias, Optional, Union

   Length: TypeAlias = str | float | int

   class Box:
       def __init__(self, w: Length, h: Optional[Length] = None, tag: Union[str, None] = None): ...

``stubpy render aliases.py`` (the defaults):

.. code-block:: python

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

   Annotations that name an alias (``Length``, ``types.Length``) keep the alias name with or
   without the import; the style applies to the alias declaration itself. See :doc:`modes`.

Deprecated ``typing`` aliases are always written in their modern form: ``List[int]`` becomes
``list[int]`` (likewise ``Dict``, ``Set``, ``FrozenSet``, ``Tuple``, ``Type``),
``ContextManager[str]`` becomes ``AbstractContextManager[str]`` from ``contextlib``, and
``Callable``, ``Iterator``, ``Mapping``, ``Sequence`` and the other abstract collections are
imported from ``collections.abc`` (``Pattern`` and ``Match`` from ``re``). Names a module
defines itself or imports from another package are left alone.

Version and platform branches
-----------------------------

Module-level and class-level ``if`` statements whose tests only compare ``sys.version_info``
(``>=``, ``<``, slices such as ``sys.version_info[:2]``) or ``sys.platform`` (``==``, ``!=``,
``startswith``), combined with ``and``, ``or`` and ``not``, are copied into the stub with
their ``elif`` and ``else`` branches, as typeshed writes them. Each branch holds the stubs of
the names it defines, and the imports it needs.

.. code-block:: python

   # compat.py
   import sys

   if sys.version_info >= (3, 11):
       from typing import Self
   else:
       from typing_extensions import Self

   if sys.platform == "win32":
       DEFAULT_SHELL = "cmd.exe"
   else:
       DEFAULT_SHELL = "/bin/sh"


   class Path:
       def joined(self, part: str) -> Self: ...

       if sys.version_info >= (3, 12):
           def walk(self) -> list[Self]: ...

``stubpy render compat.py``:

.. code-block:: python

   import sys

   if sys.version_info >= (3, 11):
       from typing import Self
   else:
       from typing_extensions import Self

   if sys.platform == 'win32':
       DEFAULT_SHELL: str
   else:
       DEFAULT_SHELL: str

   class Path:
       def joined(self, part: str) -> Self: ...

       if sys.version_info >= (3, 12):
           def walk(self) -> list[Self]: ...

The imported module only holds the branch the running interpreter took: that
branch is introspected as usual, the others are stubbed from the source. PEP 695 syntax inside
a branch (``def f[T]``, ``class C[T]``, ``type X[T] = ...``) is rewritten with ``TypeVar``,
``Generic`` and ``TypeAlias`` so the stub still parses on Python 3.10. ``if TYPE_CHECKING:``
and other tests (``if HAS_NUMPY:``) are unchanged: the ``TYPE_CHECKING`` side is stubbed, and
both sides of an unknown test are merged.

``--version-branches resolve`` (``version_branches = "resolve"``) keeps only the branch the
running interpreter takes:

.. code-block:: python

   from typing import Self

   DEFAULT_SHELL: str

   class Path:
       def joined(self, part: str) -> Self: ...
