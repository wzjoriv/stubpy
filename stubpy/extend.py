"""Extension points for advanced use: annotation handlers, the run context, symbols and diagnostics.

Examples
--------
Render a custom annotation type::

    from stubpy.extend import annotation_to_str, register_annotation_handler

    @register_annotation_handler(lambda a: isinstance(a, Validated))
    def _validated(annotation, ctx):
        return f"Validated[{annotation_to_str(annotation.inner_type, ctx)}]"

Inspect what stubpy sees in a source file without importing it::

    from stubpy.extend import ast_harvest, build_symbol_table

    table = build_symbol_table(None, "mymod", ast_harvest(source))
    print(table.all_names())
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
from .core import AliasEntry, Diagnostic, DiagnosticCollector, Level, Stage, StubContext
from .emit.annotations import annotation_to_str, register_annotation_handler

__all__ = [
    "ASTSymbols",
    "AliasEntry",
    "AliasSymbol",
    "ClassSymbol",
    "Diagnostic",
    "DiagnosticCollector",
    "FunctionSymbol",
    "Level",
    "OverloadGroup",
    "Stage",
    "StubContext",
    "SymbolKind",
    "SymbolTable",
    "VariableSymbol",
    "annotation_to_str",
    "ast_harvest",
    "build_symbol_table",
    "register_annotation_handler",
]
