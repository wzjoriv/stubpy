"""Generate ``.pyi`` stub files with full ``**kwargs`` / ``*args`` MRO backtracing.

Usage::

    from stubpy import generate_stub, generate_package, StubConfig, StubContext

    content = generate_stub("path/to/module.py")
    result = generate_package("mypackage/", "stubs/")
    print(result.summary())

    ctx = StubContext(config=StubConfig(include_private=True))
    content = generate_stub("path/to/module.py", ctx=ctx)

From the shell: ``stubpy path/to/module.py`` or ``stubpy path/to/package/ -o stubs/``.

Sub-packages
------------
config
    :class:`StubConfig`, :class:`ExecutionMode` and config-file loading.
core
    Run context, diagnostics and the ``generate_stub`` / ``generate_package`` pipeline.
analysis
    Module loading, the AST pre-pass, import scanning, aliases, the symbol
    table and docstring type inference.
resolve
    ``**kwargs`` / ``*args`` backtracing through the MRO and forwarding calls.
emit
    Stub text for classes, functions, variables, aliases and overloads.
cli
    The ``stubpy`` command.
"""
from .analysis.harvest import ASTSymbols, ast_harvest
from .analysis.symbols import (
    AliasSymbol,
    ClassSymbol,
    FunctionSymbol,
    OverloadGroup,
    SymbolKind,
    SymbolTable,
    VariableSymbol,
    build_symbol_table,
)
from .config import ExecutionMode, StubConfig, find_config_file, load_config
from .core import (
    AliasEntry,
    Diagnostic,
    DiagnosticCollector,
    DiagnosticLevel,
    DiagnosticStage,
    PackageResult,
    StubContext,
)
from .core.package import generate_package
from .core.pipeline import generate_stub
from .emit import (
    generate_alias_stub,
    generate_class_stub,
    generate_function_stub,
    generate_overload_group_stub,
    generate_variable_stub,
)
from .emit.annotations import ANNOTATION_HANDLERS as _ANN_HANDLERS
from .emit.annotations import register_annotation_handler
from .merge import MergeWarning, merge_stubs, read_and_merge, wrap_generated

__version__ = "0.6.1"
__author__ = "Josue N Rivera"

__all__ = [
    "generate_stub",
    "generate_package",
    "StubContext", "AliasEntry", "StubConfig", "ExecutionMode",
    "Diagnostic", "DiagnosticCollector", "DiagnosticLevel", "DiagnosticStage",
    "ast_harvest", "ASTSymbols",
    "SymbolTable", "SymbolKind",
    "ClassSymbol", "FunctionSymbol", "VariableSymbol", "AliasSymbol", "OverloadGroup",
    "build_symbol_table",
    "generate_class_stub", "generate_function_stub", "generate_variable_stub",
    "generate_alias_stub", "generate_overload_group_stub",
    "PackageResult",
    "register_annotation_handler", "_ANN_HANDLERS",
    "find_config_file", "load_config",
    "MergeWarning", "merge_stubs", "read_and_merge", "wrap_generated",
]
