"""
Source analysis: module loading, the AST pre-pass, imports, aliases, symbols and docstrings.
"""
from .aliases import build_alias_registry
from .docstrings import DocstringTypes, parse_docstring_types
from .harvest import ASTSymbols, ast_harvest
from .imports import (
    collect_cross_imports,
    collect_special_imports,
    collect_typing_imports,
    scan_import_statements,
)
from .loader import load_module
from .symbols import SymbolTable, build_symbol_table

__all__ = [
    "ASTSymbols",
    "DocstringTypes",
    "SymbolTable",
    "ast_harvest",
    "build_alias_registry",
    "build_symbol_table",
    "collect_cross_imports",
    "collect_special_imports",
    "collect_typing_imports",
    "load_module",
    "parse_docstring_types",
    "scan_import_statements",
]
