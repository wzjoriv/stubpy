"""
The generated regions of an existing stub: markers, their scopes and the names each one owns.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from ._merge_units import Unit, names_bound

_MARKER_RE = re.compile(r"^\ufeff?(\s*)#\s*stubpy\s*:?\s*auto[-\s]?generated\s*(begin|end)\s*$", re.IGNORECASE)


class MergeError(ValueError):
    """The existing stub cannot be merged safely.

    Raised for unbalanced or misaligned markers, or a result that does not parse.

    Examples
    --------
    >>> from stubpy.merge import merge_stubs
    >>> try:
    ...     merge_stubs("# stubpy: auto-generated begin\\n", "x: int\\n")
    ... except MergeError as exc:
    ...     print(exc)
    begin marker on line 1 has no end marker
    """


@dataclass(frozen=True)
class _Region:
    begin: int
    end: int
    indent: str
    scope: tuple[str, ...] = ()


def _marker(line: str) -> tuple[str, str] | None:
    """``(indent, "begin" | "end")`` for a marker line, else ``None``."""
    m = _MARKER_RE.match(line.rstrip("\r\n"))
    return (m.group(1), m.group(2).lower()) if m else None


def _regions(lines: list[str]) -> list[_Region]:
    """The marked regions; raises :class:`MergeError` on nested, unbalanced or misaligned markers."""
    regions: list[_Region] = []
    open_at: int | None = None
    indent = ""
    for i, line in enumerate(lines):
        found = _marker(line)
        if found is None:
            continue
        where, kind = found
        if kind == "begin":
            if open_at is not None:
                raise MergeError(f"nested begin marker on line {i + 1}: the region opened on line {open_at + 1} "
                                 "has no end marker before it")
            open_at, indent = i, where
        else:
            if open_at is None:
                raise MergeError(f"end marker on line {i + 1} has no begin marker")
            if where != indent:
                raise MergeError(f"end marker on line {i + 1} is not indented like its begin marker "
                                 f"on line {open_at + 1}")
            regions.append(_Region(open_at, i, indent))
            open_at = None
    if open_at is not None:
        raise MergeError(f"begin marker on line {open_at + 1} has no end marker")
    return regions


def _skeleton(lines: list[str], regions: list[_Region]) -> ast.Module:
    """Parse the stub with each region reduced to a ``pass`` placeholder."""
    out = [ln.rstrip("\r\n").lstrip("\ufeff") for ln in lines]
    for r in regions:
        out[r.begin] = f"{r.indent}pass"
        for i in range(r.begin + 1, r.end + 1):
            out[i] = ""
    try:
        return ast.parse("\n".join(out) + "\n")
    except SyntaxError as exc:
        raise MergeError(f"the stub does not parse outside its marked regions: {exc}") from exc


def _scope_of(tree: ast.Module, line: int) -> tuple[ast.Module | ast.ClassDef, tuple[str, ...]]:
    """The innermost class (or the module) whose body holds the placeholder on 1-based *line*."""
    node: ast.Module | ast.ClassDef = tree
    path: list[str] = []
    while True:
        inner = next((c for c in node.body if isinstance(c, ast.ClassDef)
                      and c.lineno < line <= (c.end_lineno or c.lineno)), None)
        if inner is None:
            return node, tuple(path)
        node, path = inner, [*path, inner.name]


def _placeholders(regions: list[_Region]) -> set[int]:
    return {r.begin + 1 for r in regions}


def _hand_names(scope: ast.Module | ast.ClassDef, placeholders: set[int]) -> set[str]:
    return {n for s in scope.body if not (isinstance(s, ast.Pass) and s.lineno in placeholders)
            for n in names_bound(s)}


def _old_names(lines: list[str], region: _Region) -> set[str]:
    """The names the region defines now (empty when its body does not parse on its own)."""
    body = "".join(ln[len(region.indent):] if ln.startswith(region.indent) else ln.lstrip()
                   for ln in lines[region.begin + 1:region.end])
    try:
        return {n for s in ast.parse(body).body for n in names_bound(s)}
    except SyntaxError:
        return set()


def _distribute(units: list[Unit], regions: list[_Region], old: list[set[str]]) -> list[list[Unit]]:
    """Give each unit to the region that defined one of its names, else to its predecessor's region."""
    placed: list[list[Unit]] = [[] for _ in regions]
    last = 0
    for unit in units:
        home = next((k for k, names in enumerate(old) if names & unit.names), None)
        if home is None:
            home = 0 if unit.is_import else last
        placed[home].append(unit)
        last = home
    return placed


def _body(units: list[Unit], indent: str, newline: str, needs_body: bool) -> str:
    """The region text: units in order, separated as in the generated stub, re-indented."""
    parts: list[str] = []
    prev: Unit | None = None
    for unit in units:
        if prev is not None:
            parts.append(unit.gap)
        parts.append(unit.text)
        prev = unit
    text = "".join(parts)
    if not text.strip() and needs_body:
        text = "...\n"
    lines = [f"{indent}{ln}" if ln.strip() else "" for ln in text.splitlines()]
    return "".join(ln + newline for ln in lines)


def _has_regions_inside(unit: Unit, by_scope: dict[tuple[str, ...], list[int]]) -> bool:
    return any(path and path[0] in unit.names for path in by_scope)


def _parse_generated(generated: str) -> tuple[ast.Module, list[str]]:
    text = "".join(ln for ln in generated.splitlines(keepends=True) if _marker(ln) is None)
    return ast.parse(text), text.splitlines(keepends=True)
