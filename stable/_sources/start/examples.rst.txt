Examples
========

Short scripts that use only the public API. Each one builds what it needs in a temporary
folder, so it runs as it is: ``python examples/generate_stubs.py``. The test suite runs
them all. They live in the ``examples/`` folder of the repository.

Forwarded keyword arguments
---------------------------

A class passes ``**kwargs`` to its base class; the stub lists the parameters they stand for.

.. literalinclude:: ../../examples/generate_stubs.py
   :language: python
   :lines: 2-

Render and check
----------------

``render`` builds one stub without writing it. ``check`` reports the stubs that no longer
match their source.

.. literalinclude:: ../../examples/render_and_check.py
   :language: python
   :lines: 2-

Configuration file
------------------

.. literalinclude:: ../../examples/config_file.py
   :language: python
   :lines: 2-

Hints for compiled code
-----------------------

A JIT-wrapped or compiled callable has no signature to introspect. The hints give it one.

.. literalinclude:: ../../examples/hints_for_compiled.py
   :language: python
   :lines: 2-

pre-commit
----------

.. literalinclude:: ../../examples/pre-commit-config.yaml
   :language: yaml
