.. _api_context:

stubpy.context
==============

.. automodule:: stubpy.context
   :no-members:

.. autoclass:: stubpy.context.ExecutionMode
   :no-index:
   :exclude-members: RUNTIME, AST_ONLY, AUTO

   Controls whether the target module is executed during stub generation.

   .. attribute:: RUNTIME

      Execute the module and use live objects for full introspection.
      This is the default and enables ``**kwargs`` MRO back-tracing.

   .. attribute:: AST_ONLY

      Parse the AST only; no module execution.  Safer but less precise.

   .. attribute:: AUTO

      Execute the module when possible; fall back to AST-only on load
      failures.

.. autoclass:: stubpy.context.StubConfig
   :members:
   :special-members: __init__

.. autoclass:: stubpy.context.AliasEntry
   :members:

.. autoclass:: stubpy.context.StubContext
   :members:
   :special-members: __init__

.. rubric:: Notes

:class:`StubContext` is the central state carrier for one stub-generation
run.  A fresh instance is created inside every call to
:func:`~stubpy.generator.generate_stub`, making the generator fully
re-entrant.

**v0.1 fields** (unchanged): ``alias_registry``, ``type_module_imports``,
``used_type_imports``, and the :meth:`~StubContext.lookup_alias` method.

**Added in v0.2.0**: ``config`` (:class:`StubConfig`), ``diagnostics``
(:class:`~stubpy.diagnostics.DiagnosticCollector`), ``symbol_table``
(:class:`~stubpy.symbols.SymbolTable` or ``None``), ``all_exports``
(``set[str]`` or ``None``).
