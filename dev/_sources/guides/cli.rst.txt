Command line
============

.. code-block:: text

   stubpy [generate] [TARGET ...] [-o OUT] [--dry-run] [--diff]
                                                 write stubs (the default command)
   stubpy check [TARGET ...] [-o OUT] [--diff]   exit 1 when a stub is missing or stale; writes nothing
   stubpy render TARGET                          print one stub to stdout
   stubpy docstrings {list,sync,check} [STUB ...] [-m MODULE] [--no-config]
                                                 runtime docstrings into hand-written stubs
   stubpy --version

``generate`` is implied when the first argument is not a sub-command, so ``stubpy mod.py``
and ``stubpy generate mod.py`` are the same. ``python -m stubpy`` is equivalent.

Targets
-------

A ``TARGET`` is any of:

* a ``.py`` file,
* a folder (searched recursively; a package folder uses its ``__init__.py``),
* a quoted glob such as ``"src/**/*.py"`` (stubpy expands it even when the shell does not),
* a dotted module name such as ``mypkg.core``. It must be importable: installed, or on
  ``sys.path``.

With no target, stubpy uses ``targets`` and ``modules`` from the config file.
``render`` takes exactly one target: a file or a dotted module name. A glob is accepted
only when it matches a single file.

Output
------

``-o`` / ``--output`` decides where stubs go:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - ``-o`` value
     - Result
   * - ends in ``.pyi``, one file target
     - that exact file
   * - any other path
     - a stub root: ``src/mypkg/core.py`` becomes ``<OUT>/mypkg/core.pyi`` and every package
       gets an ``__init__.pyi``
   * - not given
     - ``output_dir`` from the config, else each stub next to its source

A ``.pyi`` output with several targets is a usage error.

Options
-------

``generate``, ``check`` and ``render`` take these options. Each maps to a :doc:`configuration` key and
overrides the config file.

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Option
     - Effect
   * - ``--imports {all,none,stdlib}``
     - Which modules may be imported. By default (``all``) modules are imported and the live
       objects are merged with the source; ``none`` executes nothing and ``stdlib`` allows
       only the standard library. See :doc:`modes`.
   * - ``--allow-import NAME``
     - Also allow ``NAME`` (``pkg`` or ``pkg.*``) on top of the standard library. Repeatable.
   * - ``--deny-import NAME``
     - Never import ``NAME``. Repeatable; wins over the allowed names.
   * - ``--no-import``
     - Same as ``--imports none``.
   * - ``--include-private``
     - Stub names starting with ``_``.
   * - ``--include-docstrings``
     - Use docstrings as stub bodies.
   * - ``--infer-types``
     - Fill missing types from NumPy, Google or Sphinx docstrings.
   * - ``--incremental``
     - Merge into existing stubs, keeping edits outside the markers. See :doc:`incremental`.
   * - ``--no-resolve-kwargs``
     - Keep ``**kwargs`` as written.
   * - ``--no-resolve-args``
     - Keep ``*args`` as written.
   * - ``--no-respect-all``
     - Stub every public name even when ``__all__`` is defined.
   * - ``--union-style {modern,legacy}``
     - ``X | None`` or ``Optional[X]``.
   * - ``--alias-style {compatible,pep695,auto}``
     - ``X: TypeAlias = ...``, ``type X = ...`` or automatic.
   * - ``--version-branches {emit,resolve}``
     - Copy ``sys.version_info`` / ``sys.platform`` branches into the stub (default), or keep
       only the running interpreter's branch. See :doc:`configuration`.
   * - ``--exclude PATTERN``
     - Pattern of files or folders to skip. Repeatable; replaces the defaults (hidden files,
       build output, names Python cannot import). See :doc:`configuration`.
   * - ``--extend-exclude PATTERN``
     - Pattern to skip on top of the defaults. Repeatable.
   * - ``--show-excluded``
     - List every skipped file and the pattern that matched.
   * - ``--target-python X.Y``
     - Oldest Python the stubs must import on (``3.10``); newer ``typing`` names are imported
       from ``typing_extensions``. See :doc:`configuration`.
   * - ``--no-config``
     - Ignore ``stubpy.toml`` and ``[tool.stubpy]``.
   * - ``--verbose``
     - Print every diagnostic, INFO included.
   * - ``--strict``
     - Count warnings as failures.
   * - ``-q``, ``--quiet``
     - Print errors only.

``docstrings`` has its own options (``-m MODULE``, ``-q``); see :doc:`compiled`.

``check --diff`` prints a unified diff per stale stub. ``generate --diff`` prints the diff of each
stub it changes and writes them; ``generate --dry-run`` writes nothing and lists the stubs that
would change (with ``--diff``, their diffs). ``generate`` and ``check`` have ``-o``; ``render``
does not.

What is printed
---------------

``generate`` prints ``wrote <path>`` per stub and a summary on stdout. ``check`` prints
``stale <path>`` per stale stub (plus the diff with ``--diff``) and a summary.
Diagnostics of failed modules go to stderr; ``--verbose`` prints all of them.
``-q`` prints errors only.

.. code-block:: console

   $ stubpy render broken.py
   FAILED broken.py
       [ERROR] (ast_pass) broken.py: Source does not parse on this Python version: SyntaxError: invalid syntax (broken.py, line 3)
   $ echo $?
   1

A module that cannot be imported is not an error: it is stubbed from the source with a
WARNING (a failure under ``--strict``). A file that does not parse is an ERROR.

Exit codes are listed in :doc:`../reference/exit-codes`.

Docstrings
----------

``stubpy docstrings`` copies the docstrings of a compiled or Cython module into its
hand-written stub (see :doc:`compiled`).

.. code-block:: console

   $ stubpy docstrings list                     # module -> stub, and a count
   $ stubpy docstrings sync pkg/_native.pyi     # write the docstrings
   $ stubpy docstrings check                    # exit 1 when a stub is out of date
   $ stubpy docstrings sync -m pkg._native      # by module name

With no STUB and no ``-m``, the stubs come from the ``[tool.stubpy.docstrings]`` table of the
config file (see :doc:`configuration`). ``--no-config`` ignores the config file, so STUB or
``-m`` is then required.

Exit codes: ``0`` up to date (or synced), ``1`` out of date (``check``), ``2`` usage error or
a module that fails to import or parse. Every such failure is reported, not only the first.

Examples
--------

.. code-block:: console

   $ stubpy mod.py                              # write mod.pyi next to mod.py
   $ stubpy src/mypkg -o stubs                  # write stubs/mypkg/**/*.pyi
   $ stubpy src --extend-exclude "tests"
   $ stubpy mypkg.core -o stubs                 # by module name
   $ stubpy check src/mypkg -o stubs --diff
   $ stubpy render mypkg.core --imports none
   $ stubpy --incremental                       # targets from [tool.stubpy]
