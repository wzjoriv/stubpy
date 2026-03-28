.. _api_public:

stubpy — public API
====================

The names exported from the top-level :mod:`stubpy` package form the
stable public interface. All other names are internal and may change
between minor versions.

.. rubric:: Core

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.generator.generate_stub`
     - Load a source file, generate a stub, and write it to disk.
   * - :class:`~stubpy.context.StubContext`
     - Run-scoped state container; one instance per ``generate_stub`` call.
   * - :class:`~stubpy.context.AliasEntry`
     - Named tuple pairing an annotation object with its alias string.
   * - :class:`~stubpy.context.StubConfig`
     - Per-run configuration (execution mode, verbosity, strictness).
   * - :class:`~stubpy.context.ExecutionMode`
     - Enum: ``RUNTIME`` / ``AST_ONLY`` / ``AUTO``.

.. rubric:: Diagnostics

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :class:`~stubpy.diagnostics.DiagnosticCollector`
     - Accumulates ``Diagnostic`` records from all pipeline stages.
   * - :class:`~stubpy.diagnostics.Diagnostic`
     - Immutable record: level, stage, symbol name, message.
   * - :class:`~stubpy.diagnostics.DiagnosticLevel`
     - Enum: ``INFO`` / ``WARNING`` / ``ERROR``.
   * - :class:`~stubpy.diagnostics.DiagnosticStage`
     - Enum: ``load``, ``ast_pass``, ``symbol_table``, ``alias``,
       ``resolve``, ``emit``, ``import``, ``generator``.

.. rubric:: AST pre-pass

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.ast_pass.ast_harvest`
     - Parse source and return an :class:`~stubpy.ast_pass.ASTSymbols`
       container without executing any code.
   * - :class:`~stubpy.ast_pass.ASTSymbols`
     - Lightweight dataclass holding all harvested metadata.

.. rubric:: Symbol table

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.symbols.build_symbol_table`
     - Merge live module + AST metadata into a :class:`~stubpy.symbols.SymbolTable`.
   * - :class:`~stubpy.symbols.SymbolTable`
     - Ordered collection of :class:`~stubpy.symbols.StubSymbol` entries.
   * - :class:`~stubpy.symbols.SymbolKind`
     - Enum: ``class`` / ``function`` / ``variable`` / ``alias`` / ``overload``.
   * - :class:`~stubpy.symbols.ClassSymbol`
     - Wraps a live ``type`` object + :class:`~stubpy.ast_pass.ClassInfo`.
   * - :class:`~stubpy.symbols.FunctionSymbol`
     - Wraps a callable + ``is_async`` flag.
   * - :class:`~stubpy.symbols.VariableSymbol`
     - Module-level variable with annotated or inferred type.
   * - :class:`~stubpy.symbols.AliasSymbol`
     - ``TypeAlias`` / ``NewType`` declaration.
   * - :class:`~stubpy.symbols.OverloadGroup`
     - Multiple ``@overload`` variants sharing a name.

Full documentation for each module lives on its own page:

- :ref:`api_generator` — :func:`~stubpy.generator.generate_stub`
- :ref:`api_context` — :class:`~stubpy.context.StubContext`, :class:`~stubpy.context.StubConfig`
- :ref:`api_diagnostics` — :class:`~stubpy.diagnostics.DiagnosticCollector`
- :ref:`api_ast_pass` — :func:`~stubpy.ast_pass.ast_harvest`
- :ref:`api_symbols` — :class:`~stubpy.symbols.SymbolTable`
