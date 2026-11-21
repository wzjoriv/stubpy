stubpy.extend
=============

The advanced namespace. See :doc:`../../guides/extending` for worked examples. ``Diagnostic`` and ``Level`` are re-exported here unchanged; they are documented in :doc:`results`.

.. module:: stubpy.extend
   :no-index:

Annotation handlers
-------------------

.. autofunction:: stubpy.extend.register_annotation_handler

.. autofunction:: stubpy.extend.annotation_to_str

Forwarding resolvers and stub hooks
-----------------------------------

.. autofunction:: stubpy.extend.register_forward_resolver

.. autofunction:: stubpy.extend.register_stub_hook

Symbol table
------------

.. autofunction:: stubpy.extend.ast_harvest

.. autofunction:: stubpy.extend.build_symbol_table

.. autoclass:: stubpy.extend.SymbolTable
   :members:

.. autoclass:: stubpy.extend.ASTSymbols

.. autoclass:: stubpy.extend.ClassSymbol

.. autoclass:: stubpy.extend.FunctionSymbol

.. autoclass:: stubpy.extend.VariableSymbol

.. autoclass:: stubpy.extend.AliasSymbol

.. autoclass:: stubpy.extend.OverloadGroup

.. autoclass:: stubpy.extend.SymbolKind
   :members:
   :undoc-members:

Run context and diagnostics
---------------------------

.. autoclass:: stubpy.extend.StubContext

.. autoclass:: stubpy.extend.AliasEntry

.. autoclass:: stubpy.extend.DiagnosticCollector
   :members:

.. autoclass:: stubpy.extend.Stage
   :members:
   :undoc-members:
