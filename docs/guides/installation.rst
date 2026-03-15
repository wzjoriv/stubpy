.. _installation:

Installation
============

Requirements
------------

- Python **3.10** or newer (uses PEP 604 ``X | Y`` union syntax at runtime)
- No third-party runtime dependencies — the package uses the standard library only

From PyPI
---------

.. code-block:: bash

   pip install stubpy

From source
-----------

.. code-block:: bash

   git clone https://github.com/wzjoriv/stubpy.git
   cd stubpy
   pip install -e .

Development extras
------------------

To run the test suite and build the documentation locally, install the
optional dependency groups:

.. code-block:: bash

   # Tests (pytest + coverage)
   pip install -e ".[dev]"

   # Documentation (Sphinx + Furo theme + MyST)
   pip install -e ".[docs]"

   # Both at once
   pip install -e ".[dev,docs]"

Verifying the installation
--------------------------

.. code-block:: bash

   stubpy --help

You should see the stubpy CLI help text.  You can also verify the Python
API is importable:

.. code-block:: python

   from stubpy import generate_stub
   print("stubpy is ready")
