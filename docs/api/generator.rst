.. _api_generator:

stubpy.generator
================

.. automodule:: stubpy.generator
   :no-members:

.. rubric:: Single-file generation

.. autofunction:: stubpy.generator.generate_stub
.. autofunction:: stubpy.generator.collect_classes

.. rubric:: Package generation

.. autofunction:: stubpy.generator.generate_package
.. autoclass:: stubpy.generator.PackageResult
   :members:

.. rubric:: Pipeline stages

Each call to :func:`generate_stub` runs eight stages in order:

.. code-block:: text

   generate_stub(filepath)
       │
       ├─ 1. loader      load_module()                → module, path, name
       │        └─ (skipped in AST_ONLY; warning+fallback in AUTO)
       ├─ 2. ast_pass    ast_harvest()                → ASTSymbols
       ├─ 3. imports     scan_import_statements()     → import_map
       ├─ 4. aliases     build_alias_registry()       → ctx populated
       ├─ 5. symbols     build_symbol_table()         → SymbolTable
       ├─ 6. emitter     for each symbol (source order):
       │       ├─ AliasSymbol    → generate_alias_stub()
       │       ├─ ClassSymbol    → generate_class_stub()
       │       │       └─ for each method:
       │       │           resolver  resolve_params()
       │       │           emitter   generate_method_stub()
       │       ├─ OverloadGroup → generate_overload_group_stub()
       │       ├─ FunctionSymbol → generate_function_stub()
       │       └─ VariableSymbol → generate_variable_stub()
       ├─ 7. imports     collect_typing_imports()     → header
       │                 collect_special_imports()
       │                 collect_cross_imports()
       └─ 8. write       .pyi file written to disk

.. rubric:: Execution modes

The pipeline respects :class:`~stubpy.context.ExecutionMode`:

``RUNTIME`` (default)
    Execute the module at stage 1.  All introspection paths available.

``AST_ONLY``
    Skip stage 1 entirely.  Live types will be ``None``; stubs are built
    from AST metadata only.  Useful for modules with import-time side
    effects.

``AUTO``
    Attempt stage 1; if the load raises any exception, record a
    ``WARNING`` diagnostic and continue with AST-only data.

.. rubric:: Package processing

:func:`generate_package` calls :func:`generate_stub` for every ``.py``
file found by a recursive directory walk.  It mirrors the source tree
under the output directory and ensures every sub-package has an
``__init__.pyi``.  Files that fail are collected in
:attr:`PackageResult.failed` rather than aborting the run.
