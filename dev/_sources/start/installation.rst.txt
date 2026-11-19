Installation
============

stubpy needs Python 3.10 or newer and has no runtime dependencies. It is tested on
CPython 3.10 to 3.15 and PyPy, and it runs in Pyodide (WebAssembly).

.. code-block:: console

   $ pip install stubpy

or, with uv:

.. code-block:: console

   $ uv add --dev stubpy          # in a project
   $ uvx stubpy render mod.py     # one-off

Check the install:

.. code-block:: console

   $ stubpy --version
   stubpy 0.7.1

``python -m stubpy`` runs the same command.

Supported runtimes
------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Runtime
     - Tested in CI
   * - CPython
     - 3.10 to 3.15 on Linux; the oldest and newest also on Windows and macOS
   * - CPython free-threaded
     - 3.14t (GIL disabled)
   * - PyPy
     - 3.11
   * - GraalPy
     - 25 (Python 3.13)
   * - Pyodide
     - WebAssembly, in the browser or Node

Extras
------

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Extra
     - Installs
   * - ``docs``
     - Sphinx, Furo, MyST and the Mermaid extension, to build these docs.
   * - ``dev``
     - Everything in ``docs``, plus pytest, pytest-cov, ruff, typer and ``tomli`` on Python 3.10.

.. code-block:: console

   $ pip install "stubpy[docs]"

From source
-----------

.. code-block:: console

   $ git clone https://github.com/wzjoriv/stubpy
   $ cd stubpy
   $ pip install -e ".[dev]"

.. note::

   By default stubpy imports your modules, so run it in the environment that has
   your project's dependencies installed. If importing has side effects, set
   ``imports = "none"`` (or ``"stdlib"``, or a list such as ``["mypkg"]``) in
   ``[tool.stubpy]`` or pass ``--imports none``; stubpy then works from the source. This
   limits import-time side effects; it is not a security sandbox. See :doc:`../guides/modes`.
