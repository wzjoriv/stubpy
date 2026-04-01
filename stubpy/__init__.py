"""
stubpy
======

Generate ``.pyi`` stub files for Python modules with full ``**kwargs``
and ``*args`` MRO backtracing.

Quickstart::

    from stubpy import generate_stub, generate_package

    # Single file
    content = generate_stub("path/to/module.py")
    content = generate_stub("path/to/module.py", "out/module.pyi")

    # Entire package
    result = generate_package("mypackage/", "stubs/")
    print(result.summary())

    # Custom configuration
    from stubpy import StubContext, StubConfig
    ctx = StubContext(config=StubConfig(include_private=True))
    content = generate_stub("path/to/module.py", ctx=ctx)

CLI::

    stubpy path/to/module.py
    stubpy path/to/package/
    stubpy path/to/module.py -o out/module.pyi --print
    stubpy path/to/module.py --include-private
    stubpy path/to/module.py --verbose --strict
    stubpy path/to/module.py --typing-style legacy
"""
from .context import AliasEntry, ExecutionMode, StubConfig, StubContext
from .diagnostics import Diagnostic, DiagnosticCollector, DiagnosticLevel, DiagnosticStage
from .emitter import (
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_overload_group_stub,
    generate_variable_stub,
)
from .generator import PackageResult, collect_classes, generate_package, generate_stub
from .ast_pass import ast_harvest, ASTSymbols
from .symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    build_symbol_table,
)
from .config import find_config_file, load_config

__all__ = [
    # Core entry points
    "generate_stub",
    "generate_package",
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
    "generate_alias_stub", "generate_overload_group_stub",
    # Package processing result
    "PackageResult",
    # Configuration file support
    "find_config_file", "load_config",
]
__version__ = "0.5.0"
