.. _api_context:

stubpy.context
==============

.. automodule:: stubpy.context
   :no-members:

.. autoclass:: stubpy.context.ExecutionMode
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
   :exclude-members: alias_registry, type_module_imports, used_type_imports, config, diagnostics, symbol_table, all_exports

   Mutable state container scoped to one stub-generation run.

   Create one instance per :func:`~stubpy.generator.generate_stub` call,
   or pass a pre-configured instance to supply custom options.

   .. attribute:: config

      :class:`StubConfig` — per-run options (execution mode, privacy, etc.).

   .. attribute:: diagnostics

      :class:`~stubpy.diagnostics.DiagnosticCollector` — accumulated issues.

   .. attribute:: symbol_table

      :class:`~stubpy.symbols.SymbolTable` or ``None`` — populated after the
      symbol-table stage.

   .. attribute:: all_exports

      ``set[str]`` or ``None`` — contents of ``__all__``, when present.

   .. attribute:: alias_registry

      List of :class:`AliasEntry` — registered type aliases from sub-modules.

   .. attribute:: type_module_imports

      ``dict[str, str]`` — import statements keyed by local alias name.

   .. attribute:: used_type_imports

      ``dict[str, str]`` — subset of *type_module_imports* actually used.

   .. automethod:: stubpy.context.StubContext.lookup_alias

.. rubric:: Notes

:class:`StubContext` is the central state carrier for one stub-generation
run.  A fresh instance is created inside every call to
:func:`~stubpy.generator.generate_stub`, making the generator fully
re-entrant.
