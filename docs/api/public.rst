.. _api_public:

stubpy — public API
====================

The names exported from the top-level :mod:`stubpy` package form the
stable public interface.  All other names are internal and may change
between minor versions.

.. rubric:: Core

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.generator.generate_stub`
     - Load a source file, generate a stub, and write it to disk.
   * - :func:`~stubpy.generator.generate_package`
     - Recursively generate stubs for every ``.py`` in a package directory.
   * - :class:`~stubpy.generator.PackageResult`
     - Result of a :func:`~stubpy.generator.generate_package` run.
   * - :class:`~stubpy.context.StubContext`
     - Run-scoped state container; one instance per ``generate_stub`` call.
   * - :class:`~stubpy.context.AliasEntry`
     - Named tuple pairing an annotation object with its alias string.
   * - :class:`~stubpy.context.StubConfig`
     - Per-run configuration (execution mode, verbosity, typing style, …).
   * - :class:`~stubpy.context.ExecutionMode`
     - Enum: ``RUNTIME`` / ``AST_ONLY`` / ``AUTO``.

.. rubric:: Configuration

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.config.load_config`
     - Load a :class:`~stubpy.context.StubConfig` from the nearest config file.
   * - :func:`~stubpy.config.find_config_file`
     - Walk upward to find ``stubpy.toml`` or ``pyproject.toml [tool.stubpy]``.

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
     - ``TypeAlias`` / ``NewType`` / ``TypeVar`` declaration.
   * - :class:`~stubpy.symbols.OverloadGroup`
     - Multiple ``@overload`` variants sharing a name.

.. rubric:: Emitters

These functions are exported for use when extending or embedding stubpy.

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Name
     - Purpose
   * - :func:`~stubpy.emitter.generate_class_stub`
     - Generate the ``.pyi`` block for a class.
   * - :func:`~stubpy.emitter.generate_function_stub`
     - Generate the stub for a module-level function.
   * - :func:`~stubpy.emitter.generate_variable_stub`
     - Generate a ``name: Type`` line for a module-level variable.
   * - :func:`~stubpy.emitter.generate_alias_stub`
     - Re-emit a TypeVar / TypeAlias / NewType declaration.
   * - :func:`~stubpy.emitter.generate_overload_group_stub`
     - Emit one ``@overload`` stub per variant.

Full documentation for each module lives on its own page:

- :ref:`api_generator` — :func:`~stubpy.generator.generate_stub`, :func:`~stubpy.generator.generate_package`
- :ref:`api_context` — :class:`~stubpy.context.StubContext`, :class:`~stubpy.context.StubConfig`
- :ref:`api_config` — :func:`~stubpy.config.load_config`, :func:`~stubpy.config.find_config_file`
- :ref:`api_diagnostics` — :class:`~stubpy.diagnostics.DiagnosticCollector`
- :ref:`api_ast_pass` — :func:`~stubpy.ast_pass.ast_harvest`
- :ref:`api_symbols` — :class:`~stubpy.symbols.SymbolTable`
- :ref:`api_emitter` — all emitter functions
