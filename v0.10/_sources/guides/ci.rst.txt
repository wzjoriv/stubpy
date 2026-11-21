CI and pre-commit
=================

``stubpy check`` is the CI command. It builds every stub in memory, compares it with the file
on disk, writes nothing and sets the exit code.

.. code-block:: console

   $ stubpy check --diff
   stale stubs\mypkg\core.pyi
   --- a/stubs/mypkg/core.pyi
   +++ b/stubs/mypkg/core.pyi
   @@ -3,3 +3,4 @@
    class Client:
        def __init__(self, host: str, port: int = 80) -> None: ...
        def get(self, path: str) -> bytes: ...
   +    def close(self) -> None: ...
   Checked 2 stubs: 1 stale, 0 failed.
   $ echo $?
   1

A stub that does not exist yet counts as stale. With no arguments ``check`` acts on the
``targets`` and ``modules`` of ``[tool.stubpy]``, so the same file drives ``generate`` and
``check``.

Exit codes
----------

.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Code
     - Meaning
   * - ``0``
     - Every stub is up to date and no module failed.
   * - ``1``
     - A stub is stale or missing, a module failed to load, or a warning was raised under
       ``--strict``.
   * - ``2``
     - Usage error, an invalid config file, or a target that cannot be found.

See :doc:`../reference/exit-codes`.

pre-commit
----------

The repository ships two hooks in ``.pre-commit-hooks.yaml``. Both ignore the file names
pre-commit passes and act on the configured targets.

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - Hook id
     - Runs
     - Use
   * - ``stubpy-check``
     - ``stubpy check --diff``
     - Fail the commit when a stub is stale, and show why.
   * - ``stubpy-generate``
     - ``stubpy generate --quiet``
     - Rewrite the stubs; the commit stops when a stub changed, so you can stage the result.

.. code-block:: yaml

   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/wzjoriv/stubpy
       rev: 0.10.0
       hooks:
         - id: stubpy-check

stubpy imports your code, and pre-commit runs hooks in an isolated environment. Either list
your dependencies, or pass ``--imports none`` so nothing is imported:

.. code-block:: yaml

       hooks:
         - id: stubpy-check
           args: [--imports, none]
           additional_dependencies: [numpy]     # only if you keep the import

GitHub Actions
--------------

.. code-block:: yaml

   # .github/workflows/stubs.yml
   name: Stubs
   on: [push, pull_request]

   jobs:
     stubs:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.12"
         - run: pip install -e . stubpy
         - run: stubpy check --diff

The project is installed so that stubpy can import it. The step fails, and prints the
diff, when a committed stub no longer matches the source.

From Python
-----------

.. code-block:: python

   import stubpy

   report = stubpy.check(config=stubpy.load_config())
   for path in report.stale:
       print("stale", path)
   raise SystemExit(0 if report.ok else 1)

``report.ok`` is ``True`` when nothing is stale and nothing failed. With ``strict`` a
module that raised warnings counts as failed.
