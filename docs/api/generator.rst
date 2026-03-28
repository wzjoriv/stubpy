.. _api_generator:

stubpy.generator
================

.. automodule:: stubpy.generator
   :no-members:

.. autofunction:: stubpy.generator.generate_stub
.. autofunction:: stubpy.generator.collect_classes

.. rubric:: Pipeline sequence

Each call to :func:`generate_stub` runs these stages in order:

.. code-block:: text

   generate_stub(filepath)
       │
       ├─ 1. loader      load_module()              → module, path, name
       ├─ 2. ast_pass    ast_harvest()              → ASTSymbols
       ├─ 3. imports     scan_import_statements()   → import_map
       ├─ 4. aliases     build_alias_registry()     → ctx populated
       ├─ 5. symbols     build_symbol_table()       → SymbolTable
       ├─ 6. generator   collect_classes()          → sorted class list
       │       └─ for each class:
       │           emitter  generate_class_stub()
       │               └─ for each method:
       │                   resolver  resolve_params()
       │                   emitter   generate_method_stub()
       └─ 7. generator   assemble header + body     → write .pyi
