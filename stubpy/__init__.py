"""
stubpy
======

Generate ``.pyi`` stub files for Python modules with full ``**kwargs``
and ``*args`` MRO backtracing.

Quickstart::

    from stubpy import generate_stub

    # Write stub alongside the source and return its content
    content = generate_stub("path/to/module.py")

    # Write to a custom path
    content = generate_stub("path/to/module.py", "out/module.pyi")

    # Pass a custom context for configuration
    from stubpy import StubContext, StubConfig
    ctx = StubContext(config=StubConfig(include_private=True))
    content = generate_stub("path/to/module.py", ctx=ctx)

CLI::

    stubpy path/to/module.py
    stubpy path/to/module.py -o out/module.pyi --print
    stubpy path/to/module.py --include-private
    stubpy path/to/module.py --verbose --strict
"""
from .context import AliasEntry, ExecutionMode, StubConfig, StubContext
from .diagnostics import Diagnostic, DiagnosticCollector, DiagnosticLevel, DiagnosticStage
from .emitter import generate_class_stub, generate_function_stub, generate_variable_stub
from .generator import generate_stub
from .ast_pass import ast_harvest, ASTSymbols
from .symbols import (
    SymbolTable, SymbolKind,
    ClassSymbol, FunctionSymbol, VariableSymbol, AliasSymbol, OverloadGroup,
    build_symbol_table,
)

__all__ = [
    # Core entry point
    "generate_stub",
    # Context and configuration
    "StubContext", "AliasEntry", "StubConfig", "ExecutionMode",
    # Diagnostics
    "Diagnostic", "DiagnosticCollector", "DiagnosticLevel", "DiagnosticStage",
    # AST pre-pass
    "ast_harvest", "ASTSymbols",
    # Symbol table
    "SymbolTable", "SymbolKind",
    "ClassSymbol", "FunctionSymbol", "VariableSymbol", "AliasSymbol", "OverloadGroup",
    "build_symbol_table",
    # Emitters (public for extension)
    "generate_class_stub", "generate_function_stub", "generate_variable_stub",
]
__version__ = "0.3.0"
