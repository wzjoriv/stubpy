Quickstart
==========

The examples use this layout:

.. code-block:: text

   src/mypkg/__init__.py
   src/mypkg/core.py

.. code-block:: python

   # src/mypkg/core.py
   class Client:
       def __init__(self, host: str, port: int = 80): ...

       def get(self, path: str) -> bytes: ...

Generate
--------

``generate`` is the default command. Give it files, folders, quoted globs or dotted module
names:

.. code-block:: console

   $ stubpy src/mypkg -o stubs
   wrote stubs\mypkg\__init__.pyi
   wrote stubs\mypkg\core.pyi
   Generated 2 stubs, 0 failed.

Each module lands at its import path under the stub root, and every package gets an
``__init__.pyi``. Without ``-o`` each stub is written next to its source.

The same from Python:

.. code-block:: python

   import stubpy

   report = stubpy.generate("src/mypkg", "stubs")
   print(report.summary())      # Generated 2 stubs, 0 failed.

Check
-----

``check`` writes nothing. It exits ``1`` when a stub is missing or differs:

.. code-block:: console

   $ stubpy check src/mypkg -o stubs
   Checked 2 stubs: 0 stale, 0 failed.

After adding ``Client.close`` to the source:

.. code-block:: console

   $ stubpy check src/mypkg -o stubs --diff
   stale stubs\mypkg\core.pyi
   --- a/stubs/mypkg/core.pyi
   +++ b/stubs/mypkg/core.pyi
   @@ -3,3 +3,4 @@
    class Client:
        def __init__(self, host: str, port: int = 80) -> None: ...
        def get(self, path: str) -> bytes: ...
   +    def close(self) -> None: ...
   Checked 2 stubs: 1 stale, 0 failed.

.. code-block:: python

   report = stubpy.check("src/mypkg", "stubs")
   if not report.ok:
       raise SystemExit(report.summary())

Render
------

``render`` prints one module's stub and writes nothing:

.. code-block:: console

   $ stubpy render src/mypkg/core.py

.. code-block:: python

   result = stubpy.render("src/mypkg/core.py")
   print(result.text)
   print(result.ok, result.diagnostics)

A module that fails to load gives a result with ``ok == False`` and an ERROR diagnostic.
It does not raise.

Configure once
--------------

Put the options in ``pyproject.toml`` and the commands need no arguments:

.. code-block:: toml

   [tool.stubpy]
   targets    = ["src/mypkg"]
   output_dir = "stubs"

.. code-block:: console

   $ stubpy            # generate
   $ stubpy check      # CI

.. code-block:: python

   stubpy.generate(config=stubpy.load_config())

Relative ``targets`` and ``output_dir`` resolve against the folder that holds the file.
:doc:`../guides/configuration` lists every key.

Next
----

* :doc:`../guides/cli` for every command and flag.
* :doc:`../guides/forwarding` for what the back-tracing does.
* :doc:`../guides/ci` to run ``check`` on every commit.
* :doc:`examples` for a numbered path of runnable scripts and notebooks.
