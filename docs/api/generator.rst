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
       ├─ 1. loader     load_module()             → module, path, name
       ├─ 2. imports    scan_import_statements()  → import_map
       ├─ 3. aliases    build_alias_registry()    → ctx populated
       ├─ 4. generator  collect_classes()         → sorted class list
       │       └─ for each class:
       │           emitter  generate_class_stub()
       │               └─ for each method:
       │                   resolver  resolve_params()
       │                   emitter   generate_method_stub()
       └─ 5. generator  assemble header + body    → write .pyi
