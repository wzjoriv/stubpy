.. _api_public:

Public API reference
====================

All names exported from the top-level :mod:`stubpy` package form the stable
public interface.  Everything else is internal and may change between minor
versions.

This page is an index of public names with links to their full documentation
in the per-module API pages.  See the :ref:`api_reference` for the complete list
of modules.

All names in the tables below are hyperlinks.  Clicking any name opens its dedicated documentation page with the full parameter descriptions, examples, and a **[source]** link.

.. rubric:: Core entry points

.. autosummary::

   stubpy.generator.generate_stub
   stubpy.generator.generate_package
   stubpy.generator.PackageResult

Full documentation: :ref:`api_generator`.

.. rubric:: Configuration

.. autosummary::

   stubpy.context.StubConfig
   stubpy.context.StubContext
   stubpy.context.ExecutionMode
   stubpy.context.AliasEntry
   stubpy.config.load_config
   stubpy.config.find_config_file

Full documentation: :ref:`api_context`, :ref:`api_config`.

.. rubric:: Diagnostics

.. autosummary::

   stubpy.diagnostics.DiagnosticCollector
   stubpy.diagnostics.Diagnostic
   stubpy.diagnostics.DiagnosticLevel
   stubpy.diagnostics.DiagnosticStage

Full documentation: :ref:`api_diagnostics`.

.. rubric:: AST pre-pass

.. autosummary::

   stubpy.ast_pass.ast_harvest
   stubpy.ast_pass.ASTSymbols

Full documentation: :ref:`api_ast_pass`.

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

Full documentation: :ref:`api_symbols`.

.. rubric:: Emitters

.. autosummary::

   stubpy.emitter.generate_class_stub
   stubpy.emitter.generate_function_stub
   stubpy.emitter.generate_variable_stub
   stubpy.emitter.generate_alias_stub
   stubpy.emitter.generate_overload_group_stub

Full documentation: :ref:`api_emitter`.


.. rubric:: Per-symbol reference

Each public name also has its own dedicated page with full documentation,
parameter descriptions, examples, and a **[source]** link:

:ref:`api_reference_full`
