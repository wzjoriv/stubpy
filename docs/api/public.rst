.. _api_public:

stubpy — public API
====================

The names exported from the top-level :mod:`stubpy` package form the
stable public interface. All other names are internal and may change
between minor versions.

.. rubric:: Quick reference

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.generator.generate_stub`
     - Load a source file, generate a stub, and write it to disk.
   * - :class:`~stubpy.context.StubContext`
     - Run-scoped state container; one instance per ``generate_stub`` call.
   * - :class:`~stubpy.context.AliasEntry`
     - Named tuple pairing an annotation object with its alias string.

Full documentation for each name lives in its own module page:

- :ref:`api_generator` — :func:`~stubpy.generator.generate_stub`
- :ref:`api_context` — :class:`~stubpy.context.StubContext`, :class:`~stubpy.context.AliasEntry`
