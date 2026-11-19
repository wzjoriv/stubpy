"""
Incremental stub updates: refresh the regions of a ``.pyi`` between ``# stubpy: auto-generated begin`` and ``end`` markers.
Everything outside the regions is kept byte for byte, and a result that does not parse is never returned.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from ._constants import BEGIN_MARKER, END_MARKER
from ._merge_units import Unit, generated_units, names_bound, scope_body

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "MergeError",
    "MergeNote",
    "MergeResult",
    "merge_stubs",
    "read_and_merge",
    "wrap_generated",
]

_MARKER_RE = re.compile(r"^\ufeff?(\s*)#\s*stubpy\s*:?\s*auto[-\s]?generated\s*(begin|end)\s*$", re.IGNORECASE)


class MergeError(ValueError):
    """The existing stub cannot be merged safely.

    Raised for unbalanced or misaligned markers, or a result that does not parse.

    Examples
    --------
    >>> try:
    ...     merge_stubs("# stubpy: auto-generated begin\\n", "x: int\\n")
    ... except MergeError as exc:
    ...     print(exc)
    begin marker on line 1 has no end marker
    """


@dataclass(frozen=True)
class MergeNote:
    """One message from a merge.

    Parameters
    ----------
    level : str
        ``"info"``, ``"warning"`` or ``"error"``.
    message : str
        Human-readable description.

    Examples
    --------
    >>> MergeNote("info", "merged").level
    'info'
    """
    level: str
    message: str


@dataclass(frozen=True)
class MergeResult:
    """The outcome of a merge: the text to write and the notes it produced.

    Parameters
    ----------
    text : str or None
        The merged stub; ``None`` means leave the file as it is.
    notes : tuple of MergeNote, optional
        Messages from the merge.  Defaults to ``()``.

    Examples
    --------
    >>> MergeResult("x: int\\n").ok
    True
    >>> MergeResult(None, (MergeNote("error", "bad"),)).ok
    False
    """
    text: str | None
    notes: tuple[MergeNote, ...] = ()

    @property
    def ok(self) -> bool:
        """``True`` when no note is an error."""
        return all(n.level != "error" for n in self.notes)


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


def wrap_generated(content: str) -> str:
    """Wrap *content* in begin/end markers unless it already has one.

    Parameters
    ----------
    content : str
        Stub text.

    Returns
    -------
    str
        *content* between the markers, ending in a newline; unchanged when it
        already contains a marker.

    See Also
    --------
    merge_stubs : Refresh the marked regions of an existing stub.

    Examples
    --------
    >>> wrap_generated("x: int\\n").splitlines()
    ['# stubpy: auto-generated begin', 'x: int', '# stubpy: auto-generated end']
    """
    if any(_marker(ln) for ln in content.splitlines()):
        return content
    body = content if not content or content.endswith("\n") else content + "\n"
    return f"{BEGIN_MARKER}\n{body}{END_MARKER}\n"


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


def merge_stubs(existing: str, generated: str) -> MergeResult:
    """Refresh the marked regions of *existing* from the *generated* stub.

    Parameters
    ----------
    existing : str
        The current ``.pyi`` text, exactly as read (BOM and line endings kept).
    generated : str
        The fresh stub, with or without markers.

    Returns
    -------
    MergeResult
        The merged text and INFO notes for definitions left out because
        they are written by hand.  Without markers in *existing* the text
        is ``None`` (leave the file alone) with a WARNING.

    Raises
    ------
    MergeError
        On nested, unbalanced or misaligned markers, or when the stub
        outside the regions or the merged result does not parse.

    See Also
    --------
    read_and_merge : Merge into a stub file on disk.

    Examples
    --------
    >>> existing = "# manual\\n# stubpy: auto-generated begin\\nx: int\\n# stubpy: auto-generated end\\n"
    >>> merge_stubs(existing, "y: str\\n").text
    '# manual\\n# stubpy: auto-generated begin\\ny: str\\n# stubpy: auto-generated end\\n'
    """
    bom = "\ufeff" if existing.startswith("\ufeff") else ""
    lines = existing[len(bom):].splitlines(keepends=True)
    regions = _regions(lines)
    if not regions:
        return MergeResult(None, (MergeNote("warning", _UNMARKED),))
    tree = _skeleton(lines, regions)
    holes = _placeholders(regions)
    gen_tree, gen_lines = _parse_generated(generated)
    notes: list[MergeNote] = []
    by_scope: dict[tuple[str, ...], list[int]] = {}
    scopes: dict[tuple[str, ...], ast.Module | ast.ClassDef] = {}
    for k, r in enumerate(regions):
        scope, path = _scope_of(tree, r.begin + 1)
        by_scope.setdefault(path, []).append(k)
        scopes[path] = scope
    bodies: dict[int, str] = {}
    for path, members in by_scope.items():
        scope = scopes[path]
        hand = _hand_names(scope, holes)
        units: list[Unit] = []
        for unit in generated_units(scope_body(gen_tree, path), gen_lines):
            if unit.names and unit.names <= hand:
                if not unit.is_import and not (path == () and _has_regions_inside(unit, by_scope)):
                    where = ".".join(path) + "." if path else ""
                    notes.append(MergeNote("info", f"{where}{', '.join(sorted(unit.names))} is written by hand "
                                                   "outside the markers; the generated definition is left out"))
                continue
            units.append(unit)
        placed = _distribute(units, [regions[k] for k in members], [_old_names(lines, regions[k]) for k in members])
        only_regions = all(isinstance(s, ast.Pass) and s.lineno in holes for s in scope.body)
        for k, chosen in zip(members, placed, strict=True):
            newline = "\r\n" if lines[regions[k].begin].endswith("\r\n") else "\n"
            bodies[k] = _body(chosen, regions[k].indent, newline, bool(path) and only_regions and k == members[0])
    out: list[str] = []
    cursor = 0
    for k, r in enumerate(regions):
        out.extend(lines[cursor:r.begin + 1])
        out.append(bodies[k])
        cursor = r.end
    out.extend(lines[cursor:])
    text = bom + "".join(out)
    try:
        ast.parse(text.lstrip("\ufeff"))
    except SyntaxError as exc:
        raise MergeError(f"the merged stub would not parse ({exc}); the file is left unchanged") from exc
    return MergeResult(text, tuple(notes))


def _has_regions_inside(unit: Unit, by_scope: dict[tuple[str, ...], list[int]]) -> bool:
    return any(path and path[0] in unit.names for path in by_scope)


def _parse_generated(generated: str) -> tuple[ast.Module, list[str]]:
    text = "".join(ln for ln in generated.splitlines(keepends=True) if _marker(ln) is None)
    return ast.parse(text), text.splitlines(keepends=True)


_UNMARKED = ("has no '# stubpy: auto-generated begin/end' markers, so it is treated as hand-written and left "
             "unchanged.  Wrap the generated part in markers, or delete the file, to let --incremental update it.")


def read_and_merge(output_path: Path, generated: str) -> MergeResult:
    """Merge *generated* into the stub at *output_path*.

    A missing file gets the wrapped *generated* (the first incremental run).
    A file without markers is left alone with a WARNING; one that cannot be
    merged safely is left alone with an ERROR.

    Parameters
    ----------
    output_path : pathlib.Path
        The stub on disk, read as UTF-8.
    generated : str
        The fresh stub text.

    Returns
    -------
    MergeResult
        The text to write (``None`` to leave the file alone) and the notes.
        Problems are reported as notes, not raised.

    See Also
    --------
    merge_stubs : The merge itself, on text.

    Examples
    --------
    >>> from pathlib import Path
    >>> result = read_and_merge(Path("no_such_dir") / "m.pyi", "x: int\\n")
    >>> result.ok, result.text.splitlines()[0]
    (True, '# stubpy: auto-generated begin')
    """
    if not output_path.exists():
        return MergeResult(wrap_generated(generated), (MergeNote("info", "Incremental update: new marked stub"),))
    try:
        existing = output_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return MergeResult(None, (MergeNote("error", f"{output_path.name} is not UTF-8: {exc}"),))
    try:
        result = merge_stubs(existing, generated)
    except (MergeError, SyntaxError) as exc:
        return MergeResult(None, (MergeNote("error", f"{output_path.name}: {exc}"),))
    if result.text is None:
        return MergeResult(None, tuple(MergeNote(n.level, f"{output_path.name} {n.message}") for n in result.notes))
    return MergeResult(result.text, (MergeNote("info", "Incremental update: merged with the existing stub"),
                                     *result.notes))
