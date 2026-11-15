API Reference
=============

Every public name of the ``stubpy`` package and of :mod:`stubpy.extend`. Names starting with an
underscore and the modules behind them are internal and may change without notice.

.. toctree::
   :maxdepth: 1
   :hidden:

   functions
   config
   results
   hint
   extend

.. currentmodule:: stubpy

Functions
---------

See :doc:`functions`.

.. list-table::
   :widths: 30 70

   * - :func:`render`
     - Build the stub of one module and return it, writing nothing.
   * - :func:`generate`
     - Write stubs for files, folders, packages or modules.
   * - :func:`check`
     - Compare the stubs on disk with what would be generated.
   * - :func:`load_config`
     - Read ``[tool.stubpy]`` or ``stubpy.toml`` into a :class:`Config`.
   * - :func:`sync_docstrings`
     - Copy runtime docstrings into a hand-written stub of a compiled module.

Configuration
-------------

See :doc:`config`.

.. list-table::
   :widths: 30 70

   * - :class:`Config`
     - Frozen dataclass holding every option of a run.
   * - :class:`Mode`
     - How modules are read: ``runtime``, ``ast`` or ``auto``.
   * - :class:`~stubpy.config.UnionStyle`
     - Field type of ``Config.union_style``: ``modern`` or ``legacy``.
   * - :class:`~stubpy.config.AliasStyle`
     - Field type of ``Config.alias_style``: ``compatible``, ``pep695`` or ``auto``.

Results
-------

See :doc:`results`.

.. list-table::
   :widths: 30 70

   * - :class:`StubResult`
     - Stub text and diagnostics of one module.
   * - :class:`Report`
     - Outcome of a ``generate`` or ``check`` run over many modules.
   * - :class:`Diagnostic`
     - One message recorded while building a stub.
   * - :class:`Level`
     - Severity of a diagnostic: ``INFO``, ``WARNING`` or ``ERROR``.

Hints
-----

See :doc:`hint`.

.. list-table::
   :widths: 30 70

   * - :func:`stubpy.hint.signature`
     - Decorator that sets the stub signature of a callable.
   * - :func:`stubpy.hint.returns`
     - Decorator that sets only the return type.
   * - :func:`stubpy.hint.ignore`
     - Decorator that leaves a symbol out of the stub.

Extension namespace
-------------------

See :doc:`extend`.

.. list-table::
   :widths: 30 70

   * - :func:`stubpy.extend.register_annotation_handler`
     - Render your own annotation types.
   * - :func:`stubpy.extend.annotation_to_str`
     - Convert an annotation to stub text.
   * - :func:`stubpy.extend.ast_harvest`
     - Parse source into :class:`~stubpy.extend.ASTSymbols`.
   * - :func:`stubpy.extend.build_symbol_table`
     - Merge live and parsed data into a :class:`~stubpy.extend.SymbolTable`.
   * - :class:`~stubpy.extend.SymbolTable`
     - Every symbol of a module, by name and kind.
   * - :class:`~stubpy.extend.ASTSymbols`
     - What the parser found in a source file.
   * - :class:`~stubpy.extend.ClassSymbol`, :class:`~stubpy.extend.FunctionSymbol`,
       :class:`~stubpy.extend.VariableSymbol`, :class:`~stubpy.extend.AliasSymbol`,
       :class:`~stubpy.extend.OverloadGroup`
     - Symbol entries of the table.
   * - :class:`~stubpy.extend.SymbolKind`
     - Kind of a symbol.
   * - :class:`~stubpy.extend.StubContext`
     - State shared by one run.
   * - :class:`~stubpy.extend.AliasEntry`
     - A registered type alias.
   * - :class:`~stubpy.extend.DiagnosticCollector`
     - Collects the diagnostics of a run.
   * - :class:`~stubpy.extend.Stage`
     - Pipeline stage that raised a diagnostic.

``stubpy.__version__`` holds the installed version string.
