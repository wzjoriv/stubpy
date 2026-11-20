"""
Replace or insert docstrings in stub source text, leaving every other character as it was.
"""
from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from stubpy.analysis.docstrings.literal import docstring_literal

Node = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
Lookup = Callable[[list[str], Node], "str | None"]


@dataclass(frozen=True)
class Edit:
    """Replace ``text[start:end]`` with *new*; *name* is the qualified name of the definition."""
    start: int
    end: int
    new: str
    name: str


class _Offsets:
    """Character offsets from AST positions (whose columns are UTF-8 byte offsets)."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines(keepends=True)
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))

    def __call__(self, lineno: int, col: int) -> int:
        line = self.lines[lineno - 1] if lineno - 1 < len(self.lines) else ""
        return self.starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", "replace"))


def _is_overload(node: Node) -> bool:
    """True for ``@overload`` variants and property ``setter`` / ``deleter`` definitions."""
    return any(
        (isinstance(d, ast.Name) and d.id == "overload")
        or (isinstance(d, ast.Attribute) and d.attr in ("overload", "setter", "deleter"))
        for d in node.decorator_list
    )


def walk_definitions(tree: ast.Module) -> Iterator[tuple[list[str], Node]]:
    """Yield ``(qualified path, node)`` for top-level functions and classes and, recursively, class members."""
    def visit(body: list[ast.stmt], prefix: list[str]) -> Iterator[tuple[list[str], Node]]:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_overload(node):
                yield [*prefix, node.name], node
            elif isinstance(node, ast.ClassDef):
                yield [*prefix, node.name], node
                yield from visit(node.body, [*prefix, node.name])
    yield from visit(tree.body, [])


def _current(node: Node) -> ast.Expr | None:
    first = node.body[0] if node.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first
    return None


def _inline(stmt: ast.stmt, text_lines: list[str]) -> bool:
    """True when *stmt* shares its line with code before it (``def f(): ...`` or ``) -> T: ...``)."""
    return bool(text_lines[stmt.lineno - 1][: stmt.col_offset].strip())


def _indent(node: Node, text_lines: list[str]) -> str:
    """The indentation of *node*'s body: its first statement's on its own line, else the def's plus four spaces."""
    first = node.body[0]
    if not _inline(first, text_lines):
        line = text_lines[first.lineno - 1]
        return line[: len(line) - len(line.lstrip())]
    line = text_lines[node.lineno - 1]
    return line[: len(line) - len(line.lstrip())] + "    "


def plan_edits(text: str, lookup: Lookup) -> list[Edit]:
    """Return the edits that bring each definition's docstring in line with ``lookup(path, node)``.

    ``lookup`` returns the runtime docstring or ``None`` to leave the
    definition alone.  A body that is only ``...`` (or ``pass``) is
    replaced by the docstring; an existing docstring is replaced in place.
    """
    tree = ast.parse(text)
    offsets = _Offsets(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    edits: list[Edit] = []
    for path, node in walk_definitions(tree):
        doc = lookup(path, node)
        if doc is None or not doc.strip():
            continue
        existing = _current(node)
        if existing is not None and inspect.cleandoc(existing.value.value) == inspect.cleandoc(doc):
            continue
        indent = _indent(node, offsets.lines)
        literal = docstring_literal(doc, indent, newline)
        if literal is None:
            continue
        name = ".".join(path)
        if existing is not None:
            start = offsets(existing.lineno, existing.col_offset)
            end = offsets(existing.end_lineno or existing.lineno, existing.end_col_offset or 0)
            edits.append(Edit(start, end, literal, name))
            continue
        first = node.body[0]
        placeholder = isinstance(first, ast.Pass) or (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and first.value.value is Ellipsis)
        start = offsets(first.lineno, first.col_offset)
        if placeholder and len(node.body) == 1:
            end = offsets(first.end_lineno or first.lineno, first.end_col_offset or 0)
            if _inline(first, offsets.lines):
                while start > 0 and text[start - 1] == " ":
                    start -= 1
                gap = newline if _next_line_is_code(offsets.lines, first.end_lineno or first.lineno) else ""
                edits.append(Edit(start, end, f"{newline}{indent}{literal}{gap}", name))
            else:
                edits.append(Edit(start, end, literal, name))
        elif not _inline(first, offsets.lines):
            line = min([first.lineno, *(d.lineno for d in getattr(first, "decorator_list", []))])
            start = offsets.starts[line - 1] + len(indent)
            edits.append(Edit(start, start, f"{literal}{newline}{indent}", name))
        else:
            end = start
            while start > 0 and text[start - 1] == " ":
                start -= 1
            edits.append(Edit(start, end, f"{newline}{indent}{literal}{newline}{indent}", name))
    return edits


def _next_line_is_code(text_lines: list[str], lineno: int) -> bool:
    """True when the line after *lineno* (1-based) exists and is not blank."""
    return lineno < len(text_lines) and bool(text_lines[lineno].strip())


def apply_edits(text: str, edits: list[Edit]) -> str:
    """Apply non-overlapping *edits* to *text*."""
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        text = text[: edit.start] + edit.new + text[edit.end:]
    return text
