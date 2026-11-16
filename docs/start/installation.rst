Installation
============

stubpy needs Python 3.10 or newer and has no runtime dependencies. It is tested on
CPython 3.10 to 3.15 and PyPy.

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

   In ``runtime`` and ``auto`` mode stubpy imports your modules, so run it in the
   environment that has your project's dependencies installed.
