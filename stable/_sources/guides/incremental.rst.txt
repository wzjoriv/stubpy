Incremental updates
===================

With ``incremental = true`` (``--incremental``) stubpy writes the generated stub between two
marker comments and, on later runs, replaces only that region. Anything you wrote outside the
markers stays.

.. code-block:: console

   $ stubpy src/mypkg -o stubs --incremental

First run, with no stub on disk:

.. code-block:: python

   # stubs/mypkg/core.pyi
   # stubpy: auto-generated begin
   class Client:
       def __init__(self, host: str, port: int = 80) -> None: ...
       def get(self, path: str) -> bytes: ...
   # stubpy: auto-generated end

Add your own lines around the block:

.. code-block:: python

   # Reviewed by hand
   VERSION: str

   # stubpy: auto-generated begin
   ...
   # stubpy: auto-generated end

   class Extra:
       def run(self) -> None: ...

After ``Client.close`` is added to the source, the next ``--incremental`` run gives:

.. code-block:: python

   # Reviewed by hand
   VERSION: str

   # stubpy: auto-generated begin
   class Client:
       def __init__(self, host: str, port: int = 80) -> None: ...
       def get(self, path: str) -> bytes: ...
       def close(self) -> None: ...
   # stubpy: auto-generated end

   class Extra:
       def run(self) -> None: ...

Marker rules
------------

* The markers are ``# stubpy: auto-generated begin`` and ``# stubpy: auto-generated end``.
  They are matched without regard to case or extra whitespace.
* Several begin/end pairs may appear; each is replaced.
* A lone ``end`` extends from the start of the file; a lone ``begin`` extends to the end.
* A file that already exists but has **no markers** is treated as hand-written and left
  unchanged, with a WARNING. Start from a file produced with ``--incremental``, add the
  markers where the generated code should go, or delete the file.
* A problem while merging (for example indented markers) is reported as a WARNING on that
  module.

.. warning::

   ``check`` compares the merged text. Keep ``incremental`` on in the config when you use
   ``stubpy check`` on such stubs, or the hand edits show up as a diff.

Python API
----------

.. code-block:: python

   stubpy.generate("src/mypkg", "stubs", config=stubpy.Config(incremental=True))

The helpers behind it, ``wrap_generated``, ``merge_stubs`` and ``read_and_merge``, live in
``stubpy.merge``.
