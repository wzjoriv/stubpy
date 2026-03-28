.. _api_symbols:

stubpy.symbols
==============

.. automodule:: stubpy.symbols
   :no-members:

.. autoclass:: stubpy.symbols.SymbolKind
   :members:
   :undoc-members:

.. autoclass:: stubpy.symbols.StubSymbol
   :members:

.. autoclass:: stubpy.symbols.ClassSymbol
   :members:
   :show-inheritance:

.. autoclass:: stubpy.symbols.FunctionSymbol
   :members:
   :show-inheritance:

.. autoclass:: stubpy.symbols.VariableSymbol
   :members:
   :show-inheritance:

.. autoclass:: stubpy.symbols.AliasSymbol
   :members:
   :show-inheritance:

.. autoclass:: stubpy.symbols.OverloadGroup
   :members:
   :show-inheritance:

.. autoclass:: stubpy.symbols.SymbolTable
   :members:

.. autofunction:: stubpy.symbols.build_symbol_table

.. rubric:: Notes

:func:`build_symbol_table` merges the live module objects from
:func:`~stubpy.loader.load_module` with the AST metadata from
:func:`~stubpy.ast_pass.ast_harvest`.  When the module is ``None``
(AST-only mode), all ``live_*`` fields on every symbol are ``None``.

The table preserves **source-definition order** so that the emitted
``.pyi`` mirrors the original file layout.  Use
:meth:`~SymbolTable.sorted_by_line` to retrieve symbols in ascending
``lineno`` order regardless of insertion order.

When ``__all__`` is present in the source, :func:`build_symbol_table`
accepts an ``all_exports`` set and filters out any symbol whose name is
not in that set.  Private names (those starting with ``_``) are always
excluded regardless of ``all_exports``.
