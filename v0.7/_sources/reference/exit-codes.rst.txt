Exit codes and diagnostics
==========================

Exit codes
----------

.. list-table::
   :header-rows: 1
   :widths: 10 40 50

   * - Code
     - Meaning
     - Typical cause
   * - ``0``
     - Success
     - Stubs written (``generate``), up to date (``check``, ``docstrings check``), or printed
       (``render``).
   * - ``1``
     - Stale stubs or failed modules
     - ``check`` found a missing or differing stub, or ``docstrings check`` an out-of-date
       one; a module raised while importing or
       generating; a warning under ``--strict``.
   * - ``2``
     - Usage error
     - A target that does not exist or is not Python, a module name that cannot be imported
       when resolving a target, an invalid or unknown key in the config file, ``-o x.pyi``
       with several targets, or no target given or configured. ``docstrings`` also exits 2
       when the module behind a stub cannot be imported.

A usage error prints ``stubpy: error: <message>`` to stderr:

.. code-block:: console

   $ stubpy nonexist
   stubpy: error: No module named 'nonexist'
   $ echo $?
   2

.. code-block:: console

   $ stubpy        # with a stubpy.toml that contains: execution_mode = "auto"
   stubpy: error: .../stubpy.toml: Unknown stubpy option 'execution_mode'
   $ echo $?
   2

Diagnostics
-----------

Everything that goes wrong, or is worth noting, while building a stub is recorded as a
:class:`~stubpy.Diagnostic` instead of being raised. Each has a level, a stage, the symbol
being processed and a message.

.. list-table::
   :header-rows: 1
   :widths: 14 56 30

   * - Level
     - Meaning
     - Effect on the run
   * - ``INFO``
     - Progress notes, such as how many symbols were found.
     - Shown with ``--verbose``.
   * - ``WARNING``
     - Something was approximated; the stub is still usable.
     - Exit code ``1`` only with ``--strict``.
   * - ``ERROR``
     - The module could not be stubbed.
     - The module is not written; exit code ``1``. The other modules still run.

Stages: ``load``, ``ast_pass``, ``symbol_table``, ``alias``, ``resolve``, ``emit``,
``import`` and ``generator``.

.. code-block:: python

   result = stubpy.render("broken.py")
   for d in result.diagnostics:
       print(d)
   # [ERROR] (load) broken.py: Module execution failed: ModuleNotFoundError: No module named 'not_installed_pkg'

Quiet and verbose
-----------------

``--quiet`` prints errors only. ``--verbose`` prints every diagnostic, INFO included.
Diagnostics of failed modules are always printed, to stderr.
