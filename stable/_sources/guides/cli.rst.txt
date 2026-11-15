Command line
============

.. code-block:: text

   stubpy [generate] [TARGET ...] [-o OUT]       write stubs (the default command)
   stubpy check [TARGET ...] [-o OUT] [--diff]   exit 1 when a stub is missing or stale; writes nothing
   stubpy render TARGET                          print one stub to stdout
   stubpy docstrings {sync,check} [STUB ...] [-m MODULE]
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

All three sub-commands take these options. Each maps to a :doc:`configuration` key and
overrides the config file.

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Option
     - Effect
   * - ``--mode {runtime,ast,auto}``
     - ``runtime`` imports the module (default), ``ast`` parses only, ``auto`` is runtime
       with an AST fallback. See :doc:`modes`.
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
     - Glob, relative to a folder target, of files to skip. Repeatable; appended to the
       file's ``exclude``.
   * - ``--no-config``
     - Ignore ``stubpy.toml`` and ``[tool.stubpy]``.
   * - ``--verbose``
     - Print every diagnostic, INFO included.
   * - ``--strict``
     - Count warnings as failures.
   * - ``-q``, ``--quiet``
     - Print errors only.

``docstrings`` has its own options (``-m MODULE``, ``-q``); see :doc:`compiled`.

Only ``check`` has ``--diff`` (a unified diff per stale stub). ``generate`` and ``check``
have ``-o``; ``render`` does not.

What is printed
---------------

``generate`` prints ``wrote <path>`` per stub and a summary on stdout. ``check`` prints
``stale <path>`` per stale stub (plus the diff with ``--diff``) and a summary.
Diagnostics of failed modules go to stderr; ``--verbose`` prints all of them.
``-q`` prints errors only.

.. code-block:: console

   $ stubpy render broken.py
   FAILED broken.py
       [ERROR] (load) broken.py: Module execution failed: ModuleNotFoundError: No module named 'not_installed_pkg'
   $ echo $?
   1

Exit codes are listed in :doc:`../reference/exit-codes`.

Examples
--------

.. code-block:: console

   $ stubpy mod.py                              # write mod.pyi next to mod.py
   $ stubpy src/mypkg -o stubs                  # write stubs/mypkg/**/*.pyi
   $ stubpy src --exclude "tests/*"
   $ stubpy mypkg.core -o stubs                 # by module name
   $ stubpy check src/mypkg -o stubs --diff
   $ stubpy render mypkg.core --mode ast
   $ stubpy --incremental                       # targets from [tool.stubpy]
