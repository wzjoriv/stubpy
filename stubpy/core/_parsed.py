"""
One parse per source file: what the pipeline needs from the tree, kept without the tree itself.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from stubpy.analysis import vfs
from stubpy.analysis.astutil import is_version_test
from stubpy.analysis.harvest import ASTSymbols, ast_harvest
from stubpy.analysis.imports import scan_import_statements
from stubpy.analysis.lazy import LazyExports, static_lazy_exports

from ._constants import VERSION_TEST_MARKERS


@dataclass(frozen=True)
class ParsedFile:
    """The parts of a parsed source the pipeline reads, tied to the text they came from."""
    digest: tuple[int, int]
    import_map: dict[str, str]
    lazy: LazyExports | None
    version_test: bool


def source_digest(source: str) -> tuple[int, int]:
    """Return a cheap fingerprint of *source*."""
    return len(source), hash(source)


def has_version_test(source: str, tree: ast.Module) -> bool:
    """True when *tree* has an ``if`` on ``sys.version_info`` / ``sys.platform``, whose branches harvest differently."""
    if not any(marker in source for marker in VERSION_TEST_MARKERS):
        return False
    return any(isinstance(node, ast.If) and is_version_test(node.test) for node in ast.walk(tree))


def parsed_facts(source: str, tree: ast.Module) -> ParsedFile:
    """Return the :class:`ParsedFile` of *source*, already parsed as *tree*."""
    return ParsedFile(source_digest(source), scan_import_statements(tree), static_lazy_exports(tree),
                      has_version_test(source, tree))


def parse_file(path: Path) -> tuple[ASTSymbols | None, ParsedFile | None]:
    """Read, parse and harvest *path* once; ``(None, None)`` when it cannot be read or parsed."""
    try:
        source = vfs.read_source(path)
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return None, None
    return ast_harvest(source, tree=tree), parsed_facts(source, tree)
