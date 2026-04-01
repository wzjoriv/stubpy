.. _api_public:

Public API reference
====================

All names exported from the top-level :mod:`stubpy` package are listed here.
These form the stable public interface; all other names are internal and may
change between minor versions.

.. rubric:: Core entry points

.. autosummary::

   stubpy.generator.generate_stub
   stubpy.generator.generate_package

.. autofunction:: stubpy.generator.generate_stub
.. autofunction:: stubpy.generator.generate_package
.. autoclass:: stubpy.generator.PackageResult
   :members:

.. rubric:: Configuration

.. autosummary::

   stubpy.context.StubConfig
   stubpy.context.StubContext
   stubpy.context.ExecutionMode
   stubpy.context.AliasEntry
   stubpy.config.load_config
   stubpy.config.find_config_file

.. autoclass:: stubpy.context.StubConfig
   :no-index:
   :members:

.. autoclass:: stubpy.context.StubContext
   :no-index:
   :exclude-members: alias_registry, type_module_imports, used_type_imports, config, diagnostics, symbol_table, all_exports

   Mutable state carrier for one stub-generation run.  One fresh instance is
   created per :func:`~stubpy.generator.generate_stub` call.

   .. attribute:: config
      :type: StubConfig

      Per-run options.

   .. attribute:: diagnostics
      :type: stubpy.diagnostics.DiagnosticCollector

      Accumulated issues from all pipeline stages.

   .. attribute:: symbol_table
      :type: stubpy.symbols.SymbolTable or None

      Populated after stage 5 (symbol table build).

   .. attribute:: all_exports
      :type: set[str] or None

      Contents of ``__all__``, when present.

   .. automethod:: stubpy.context.StubContext.lookup_alias

.. autoclass:: stubpy.context.ExecutionMode
   :no-index:
   :exclude-members: RUNTIME, AST_ONLY, AUTO

   Controls whether the target module is executed.

   .. attribute:: RUNTIME

      Execute the module; full introspection available.  Default.

   .. attribute:: AST_ONLY

      No module execution.  Safe for modules with heavy import-time side
      effects.

   .. attribute:: AUTO

      Try runtime execution; fall back to AST-only on load failure.

.. autoclass:: stubpy.context.AliasEntry
   :no-index:
   :members:

.. autofunction:: stubpy.config.load_config
.. autofunction:: stubpy.config.find_config_file

.. rubric:: Diagnostics

.. autosummary::

   stubpy.diagnostics.DiagnosticCollector
   stubpy.diagnostics.Diagnostic
   stubpy.diagnostics.DiagnosticLevel
   stubpy.diagnostics.DiagnosticStage

.. autoclass:: stubpy.diagnostics.DiagnosticCollector
   :no-index:
   :members: add, info, warning, error, has_errors, has_warnings, summary, format_all, clear

.. autoclass:: stubpy.diagnostics.Diagnostic
   :no-index:
   :members:

.. autoclass:: stubpy.diagnostics.DiagnosticLevel
   :no-index:

.. autoclass:: stubpy.diagnostics.DiagnosticStage
   :no-index:

.. rubric:: AST pre-pass

.. autosummary::

   stubpy.ast_pass.ast_harvest
   stubpy.ast_pass.ASTSymbols

.. autofunction:: stubpy.ast_pass.ast_harvest
.. autoclass:: stubpy.ast_pass.ASTSymbols
   :no-index:
   :members:

.. rubric:: Symbol table

.. autosummary::

   stubpy.symbols.build_symbol_table
   stubpy.symbols.SymbolTable
   stubpy.symbols.SymbolKind
   stubpy.symbols.ClassSymbol
   stubpy.symbols.FunctionSymbol
   stubpy.symbols.VariableSymbol
   stubpy.symbols.AliasSymbol
   stubpy.symbols.OverloadGroup

.. autofunction:: stubpy.symbols.build_symbol_table
.. autoclass:: stubpy.symbols.SymbolTable
   :no-index:
   :members: add, get, get_class, get_function, by_kind, classes, functions, variables, aliases, overload_groups, all_names, sorted_by_line
.. autoclass:: stubpy.symbols.SymbolKind
   :no-index:
.. autoclass:: stubpy.symbols.ClassSymbol
   :no-index:
.. autoclass:: stubpy.symbols.FunctionSymbol
   :no-index:
.. autoclass:: stubpy.symbols.VariableSymbol
   :no-index:
.. autoclass:: stubpy.symbols.AliasSymbol
   :no-index:
.. autoclass:: stubpy.symbols.OverloadGroup
   :no-index:

.. rubric:: Emitters

.. autosummary::

   stubpy.emitter.generate_class_stub
   stubpy.emitter.generate_function_stub
   stubpy.emitter.generate_variable_stub
   stubpy.emitter.generate_alias_stub
   stubpy.emitter.generate_overload_group_stub

.. autofunction:: stubpy.emitter.generate_class_stub
.. autofunction:: stubpy.emitter.generate_function_stub
.. autofunction:: stubpy.emitter.generate_variable_stub
.. autofunction:: stubpy.emitter.generate_alias_stub
.. autofunction:: stubpy.emitter.generate_overload_group_stub
