.. _api_reference_full:

Full API reference
==================

Each public symbol has its own page with full documentation,
examples, and source links.

.. toctree::
   :maxdepth: 1
   :caption: Core entry points

   generate_stub
   generate_package
   PackageResult

.. toctree::
   :maxdepth: 1
   :caption: Configuration

   StubConfig
   StubContext
   ExecutionMode
   AliasEntry
   load_config
   find_config_file

.. toctree::
   :maxdepth: 1
   :caption: Diagnostics

   DiagnosticCollector
   Diagnostic
   DiagnosticLevel
   DiagnosticStage

.. toctree::
   :maxdepth: 1
   :caption: AST pre-pass

   ast_harvest
   ASTSymbols
   FunctionInfo
   ClassInfo
   VariableInfo
   TypeVarInfo

.. toctree::
   :maxdepth: 1
   :caption: Symbol table

   build_symbol_table
   SymbolTable
   ClassSymbol
   FunctionSymbol
   VariableSymbol
   AliasSymbol
   OverloadGroup

.. toctree::
   :maxdepth: 1
   :caption: Emitters

   generate_class_stub
   generate_function_stub
   generate_variable_stub
   generate_alias_stub
   generate_overload_group_stub

.. toctree::
   :maxdepth: 1
   :caption: Annotation dispatch

   annotation_to_str
   register_annotation_handler
   default_to_str
   format_param
