"""
Incremental stub updates: refresh the regions of a ``.pyi`` between ``# stubpy: auto-generated begin`` and ``end`` markers.
Everything outside the regions is kept byte for byte, and a result that does not parse is never returned.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from ._constants import BEGIN_MARKER, END_MARKER
from ._merge_regions import (
    MergeError,
    _body,
    _distribute,
    _hand_names,
    _has_regions_inside,
    _marker,
    _old_names,
    _parse_generated,
    _placeholders,
    _regions,
    _scope_of,
    _skeleton,
)
from ._merge_units import Unit, generated_units, scope_body

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
