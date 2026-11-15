"""The ``stubpy`` argument parser."""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``stubpy`` command."""
    p = argparse.ArgumentParser(
        prog="stubpy",
        description=(
            "Generate .pyi stub files for Python source files or package "
            "directories, with full **kwargs / *args backtracing."
        ),
    )
    p.add_argument(
        "paths",
        nargs="+",
        metavar="path",
        help=(
            "One or more .py files, package directories, or quoted glob "
            'patterns (e.g. "src/*.py").  Directories are processed '
            "recursively.  When multiple paths are given, -o is ignored."
        ),
    )
    p.add_argument(
        "-o", "--output",
        metavar="PATH",
        help=(
            "Output path.  For a single file: the .pyi file to write.  "
            "For a directory: the root output directory.  Defaults to "
            "alongside the source.  Ignored when multiple paths are given."
        ),
    )
    p.add_argument(
        "--print",
        action="store_true",
        help="Print the generated stub to stdout (single-file mode only).",
    )
    p.add_argument(
        "--include-private",
        action="store_true",
        help="Include symbols whose names start with '_'.",
    )
    p.add_argument(
        "--include-docstrings",
        action="store_true",
        help=(
            "Embed each symbol's docstring as a triple-quoted string body "
            "instead of '...'.  Useful when stubs double as documentation."
        ),
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print INFO / WARNING / ERROR diagnostics to stderr.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any ERROR diagnostic was recorded.",
    )
    p.add_argument(
        "--execution-mode",
        metavar="MODE",
        choices=["runtime", "ast_only", "auto"],
        help=(
            "'runtime' (default): execute the module.  "
            "'ast_only': parse only, no import.  "
            "'auto': runtime with AST-only fallback."
        ),
    )
    p.add_argument(
        "--union-style",
        metavar="STYLE",
        choices=["modern", "legacy"],
        help=(
            "'modern' (default, PEP 604): emits str | None.  "
            "'legacy': emits Optional[str]."
        ),
    )
    p.add_argument(
        "--alias-style",
        metavar="STYLE",
        choices=["compatible", "pep695", "auto"],
        help=(
            "'compatible' (default): Name: TypeAlias = rhs.  "
            "'pep695': type Name = rhs (Python 3.12+).  "
            "'auto': selects based on runtime Python version."
        ),
    )
    p.add_argument(
        "--infer-types",
        action="store_true",
        help=(
            "Infer parameter/return types from NumPy, Google, or Sphinx "
            "docstrings for unannotated functions.  Types emitted as "
            "'# type:' comments to distinguish them from real annotations."
        ),
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Wrap generated stub in '# stubpy: auto-generated begin/end' "
            "markers and merge into existing .pyi, preserving manual edits "
            "outside the markers."
        ),
    )
    p.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        dest="exclude",
        help=(
            "Glob pattern for files to skip during package processing "
            "(e.g. '**/test_*.py').  May be repeated for multiple patterns: "
            "--exclude '**/migrations/*' --exclude 'setup.py'."
        ),
    )
    p.add_argument(
        "--no-respect-all",
        action="store_true",
        help=(
            "Stub all public symbols even if __all__ is defined.  "
            "By default (without this flag) only names listed in __all__ "
            "are stubbed when __all__ is present."
        ),
    )
    p.add_argument(
        "--no-resolve-kwargs",
        action="store_true",
        help=(
            "Keep **kwargs / **kw as-is without expanding them into concrete "
            "named parameters.  Useful for typeshed-style stubs where "
            "``**kwargs: Any`` is the idiomatic convention."
        ),
    )
    p.add_argument(
        "--no-resolve-args",
        action="store_true",
        help="Keep *args as-is without expanding into typed positional params.",
    )
    p.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore stubpy.toml and pyproject.toml [tool.stubpy].",
    )
    return p
