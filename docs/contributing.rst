Contributing
============

Setup
-----

.. code-block:: console

   $ git clone https://github.com/wzjoriv/stubpy
   $ cd stubpy
   $ pip install -e ".[dev]"

Developer commands
------------------

``scripts/dev.py`` wraps the day-to-day tasks:

.. code-block:: console

   $ python scripts/dev.py --help

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Command
     - What it does
   * - ``dev.py check``
     - Lint, tests, docs without warnings and the project's own checks; non-zero when one
       fails.
   * - ``dev.py test [tier]``
     - Runs a test tier (default ``quick``, the whole suite, quiet); memory-capped and
       logged. ``cov`` adds a coverage report.
   * - ``dev.py docs [--open] [--clean]``
     - Builds the HTML docs.
   * - ``dev.py stubpy self-stub``
     - Stubs the stubpy package with and without importing it; non-zero when a file fails or a stub does not
       parse.
   * - ``dev.py stubpy corpus``
     - Regenerates the stubs of the pure-Python test corpus in ``corpora/`` with this checkout and lists the stubs whose text
       changed.
   * - ``dev.py stubpy raster``
     - Stubs the compiled test corpus in ``corpora/``, compiled modules included; non-zero when a file fails.
   * - ``dev.py corpora svgraster build [--clean]``
     - Builds the native modules of the compiled corpus in place, single-threaded.

Run ``dev.py check`` before opening a pull request.

Lint
----

The project uses `ruff <https://docs.astral.sh/ruff/>`_ (line length 110, target Python 3.10).

.. code-block:: console

   $ ruff check stubpy scripts tests

Tests
-----

``tests/`` mirrors the package: ``tests/analysis/``, ``tests/emit/``, ``tests/resolve/``,
``tests/config/``, ``tests/core/``, ``tests/cli/``, ``tests/compiled/``, plus ``tests/integration/`` and a few
top-level files (``test_hint.py``, ``test_merge.py``). Put a new test next to the code it
covers.

.. code-block:: console

   $ python scripts/dev.py test
   $ pytest tests/emit -q

Package boundaries
------------------

Two tests enforce the structure:

* ``tests/test_package_boundaries.py``: a module or sub-package whose name starts with ``_``
  belongs to its parent package only; ``analysis`` and ``resolve`` never import ``emit``,
  ``core.pipeline`` or ``core.api``; ``emit`` never imports ``core.pipeline`` or
  ``core.api``.
* ``tests/test_package_exports.py``: the names in ``stubpy.__all__`` match the public API.

See :doc:`explanation/architecture` for the layout. Docstrings use the NumPy style for public
API; one line is enough for simple internals.

Docs
----

The docs use Sphinx with Furo and MyST. The build treats warnings as errors:

.. code-block:: console

   $ pip install -e ".[docs]"
   $ python scripts/dev.py docs --open
   $ sphinx-build -b html -W --keep-going docs docs/_build/html

Every example in the guides is real ``stubpy`` output. When behaviour changes, rerun the
example and update the page. Pushes to ``main`` publish the ``dev`` docs and releases publish
``stable``.
