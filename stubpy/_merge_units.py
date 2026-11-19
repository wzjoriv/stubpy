"""Generated statements as merge units: their dedented text, the names they bind, and the gap before them."""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    """One generated statement (with its decorators); *gap* is the text between it and its predecessor."""
    index: int
    text: str
    names: frozenset[str]
    gap: str
    is_import: bool


def names_bound(stmt: ast.stmt) -> set[str]:
    """The names a statement binds in its scope, ``if`` / ``try`` branches included."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {stmt.name}
    if isinstance(stmt, ast.Assign):
        return {n.id for t in stmt.targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    if isinstance(stmt, (ast.AnnAssign, ast.AugAssign)) and isinstance(stmt.target, ast.Name):
        return {stmt.target.id}
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in stmt.names if a.name != "*"}
    if type(stmt).__name__ == "TypeAlias":
        return {stmt.name.id}  # type: ignore[attr-defined]
    found: set[str] = set()
    for field in ("body", "orelse", "finalbody", "handlers"):
        for child in getattr(stmt, field, []):
            if isinstance(child, ast.excepthandler):
                for inner in child.body:
                    found |= names_bound(inner)
            elif isinstance(child, ast.stmt):
                found |= names_bound(child)
    return found


def scope_body(tree: ast.Module, path: tuple[str, ...]) -> list[ast.stmt]:
    """The statements of the module, or of the class at *path* (``[]`` when it is not generated)."""
    body: list[ast.stmt] = tree.body
    for name in path:
        cls = next((s for s in body if isinstance(s, ast.ClassDef) and s.name == name), None)
        if cls is None:
            return []
        body = cls.body
    return body


def _start(stmt: ast.stmt) -> int:
    decorators = getattr(stmt, "decorator_list", [])
    return min([stmt.lineno, *(d.lineno for d in decorators)])


def generated_units(body: list[ast.stmt], lines: list[str]) -> list[Unit]:
    """Split *body* into units, dedented to column zero; docstrings and ``...`` placeholders are skipped."""
    units: list[Unit] = []
    prev_end: int | None = None
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            prev_end = stmt.end_lineno
            continue
        if isinstance(stmt, ast.Pass):
            continue
        first, last = _start(stmt), stmt.end_lineno or stmt.lineno
        col = stmt.col_offset
        text = "".join(ln[col:] if ln[:col].strip() == "" else ln.lstrip() for ln in lines[first - 1:last])
        gap = "".join(ln[col:] if ln.strip() else "\n" for ln in lines[prev_end:first - 1]) if prev_end else "\n"
        units.append(Unit(len(units), text if text.endswith("\n") else text + "\n", frozenset(names_bound(stmt)),
                          gap, isinstance(stmt, (ast.Import, ast.ImportFrom))))
        prev_end = last
    return units
