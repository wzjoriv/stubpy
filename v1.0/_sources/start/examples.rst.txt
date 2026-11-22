Examples
========

A numbered learning path of short scripts that use only the public API, from first steps to
advanced. Each builds what it needs in a temporary folder (or in ``STUBPY_EXAMPLES_OUT`` if set),
so it runs as it is: ``python examples/01_render_a_module.py``. Each also has a notebook with
its output next to it. The test suite runs them all. They live in the ``examples/`` folder of the
repository.

Render one module
-----------------

``render`` builds one stub without writing it.

.. literalinclude:: ../../examples/01_render_a_module.py
   :language: python
   :lines: 4-

Forwarded keyword arguments
---------------------------

A class passes ``**kwargs`` to its base class; the stub lists the parameters they stand for.

.. literalinclude:: ../../examples/02_forwarded_kwargs.py
   :language: python
   :lines: 4-

Generate a package
------------------

``generate`` writes the stubs of a package and returns a report.

.. literalinclude:: ../../examples/03_generate_a_package.py
   :language: python
   :lines: 4-

Check for stale stubs
---------------------

``check`` reports the stubs that no longer match their source.

.. literalinclude:: ../../examples/04_check_for_stale_stubs.py
   :language: python
   :lines: 4-

Configuration file
------------------

``load_config`` reads the ``[tool.stubpy]`` table.

.. literalinclude:: ../../examples/05_config_file.py
   :language: python
   :lines: 4-

Hints for compiled code
-----------------------

A JIT-wrapped or compiled callable has no signature to introspect. The hints give it one.

.. literalinclude:: ../../examples/06_hints_for_compiled.py
   :language: python
   :lines: 4-

Cython sources
--------------

An unbuilt ``.pyx`` is stubbed from its source alone.

.. literalinclude:: ../../examples/07_compiled_from_pyx.py
   :language: python
   :lines: 4-

Docstring sync
--------------

``sync_docstrings`` copies runtime docstrings into a hand-written stub.

.. literalinclude:: ../../examples/08_sync_docstrings.py
   :language: python
   :lines: 4-

pre-commit
----------

.. literalinclude:: ../../examples/pre-commit-config.yaml
   :language: yaml
