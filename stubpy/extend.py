"""
Extension points for advanced use: annotation handlers, the run context, symbols and diagnostics.
Everything here is re-exported from its defining module; see those for details.
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
from .emit.annotations import annotation_to_str, register_annotation_handler
from .state import AliasEntry, Diagnostic, DiagnosticCollector, Level, Stage, StubContext

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
