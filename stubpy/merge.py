"""Incremental stub updates: merge generated stubs into an existing ``.pyi``.

Generated content sits between ``# stubpy: auto-generated begin`` and
``# stubpy: auto-generated end`` markers; on later runs only the marked
regions are replaced and everything outside them is kept.  Markers are
matched case- and whitespace-insensitively, several pairs may appear, and a
lone ``end`` / ``begin`` extends to the start / end of the file.
"""
from __future__ import annotations

import re
from pathlib import Path

from ._constants import BEGIN_MARKER, END_MARKER

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "MergeWarning",
    "has_indented_markers",
    "merge_stubs",
    "read_and_merge",
    "wrap_generated",
]

_BEGIN_RE = re.compile(
    r"^\s*#\s*stubpy\s*:?\s*auto[-\s]?generated\s*begin\s*$",
    re.IGNORECASE,
)
_END_RE = re.compile(
    r"^\s*#\s*stubpy\s*:?\s*auto[-\s]?generated\s*end\s*$",
    re.IGNORECASE,
)


class MergeWarning(str):
    """A non-fatal merge issue, returned as the second value of :func:`read_and_merge`."""


def _is_begin(line: str) -> bool:
    """Return ``True`` if *line* is a begin marker."""
    return bool(_BEGIN_RE.match(line.rstrip("\n")))


def _is_end(line: str) -> bool:
    """Return ``True`` if *line* is an end marker."""
    return bool(_END_RE.match(line.rstrip("\n")))


def wrap_generated(content: str) -> str:
    """Wrap *content* in begin/end markers unless it already has a begin marker.

    Parameters
    ----------
    content : str
        A complete stub.

    Returns
    -------
    str
        The wrapped stub, ending with a newline.

    Examples
    --------
    >>> wrap_generated("x: int\\n").splitlines()
    ['# stubpy: auto-generated begin', 'x: int', '# stubpy: auto-generated end']
    """
    if any(_is_begin(ln) for ln in content.splitlines()):
        return content

    lines = [BEGIN_MARKER + "\n", content]
    if not content.endswith("\n"):
        lines.append("\n")
    lines.append(END_MARKER + "\n")
    return "".join(lines)


def merge_stubs(existing: str, generated: str) -> str:
    """Replace the marked regions of *existing* with the sections of *generated*.

    When *existing* has no markers it is kept whole and *generated* is
    appended as a new marked section.  Indented (class-body) markers are
    re-indented on merge; a whole-file stub must not be merged into them —
    :func:`read_and_merge` checks for that.

    Parameters
    ----------
    existing : str
        Current ``.pyi`` content.
    generated : str
        Fresh stub content, usually already passed through :func:`wrap_generated`.

    Returns
    -------
    str
        The merged content.

    Examples
    --------
    >>> existing = "# manual\\n# stubpy: auto-generated begin\\nx: int\\n# stubpy: auto-generated end\\n"
    >>> generated = "# stubpy: auto-generated begin\\ny: str\\n# stubpy: auto-generated end\\n"
    >>> merged = merge_stubs(existing, generated)
    >>> "y: str" in merged and "# manual" in merged and "x: int" not in merged
    True
    """
    existing_lines = existing.splitlines(keepends=True)
    generated_sections = _extract_generated_sections(generated)

    if not _has_any_marker(existing_lines):
        suffix = "" if existing.endswith("\n") else "\n"
        return existing + suffix + wrap_generated(generated)

    return _replace_marked_sections(existing_lines, generated_sections)


def has_indented_markers(text: str) -> bool:
    """Return ``True`` if any begin/end marker in *text* is indented (a class-body marker)."""
    for line in text.splitlines():
        if (_is_begin(line) or _is_end(line)) and _detect_indent(line):
            return True
    return False


def read_and_merge(
    output_path: Path,
    generated: str,
) -> tuple[str, MergeWarning | None]:
    """Merge *generated* into the file at *output_path*, if it exists.

    Parameters
    ----------
    output_path : Path
        The existing ``.pyi``.  When missing, the wrapped *generated* is returned.
    generated : str
        Fresh stub content.

    Returns
    -------
    merged : str
        Content to write to *output_path*.
    warning : MergeWarning or None
        Set when the file has class-body markers; the stub is then appended
        instead of merged, since injecting a whole file into a class body
        would be invalid.
    """
    wrapped = wrap_generated(generated)
    if not output_path.exists():
        return wrapped, None
    existing = output_path.read_text(encoding="utf-8")
    if has_indented_markers(existing):
        warning = MergeWarning(
            f"{output_path.name} contains class-body markers "
            "(indented '# stubpy: auto-generated begin/end').  "
            "The incremental generator works at file granularity and cannot "
            "safely inject a whole-file stub inside a class block.  "
            "The new stub has been APPENDED rather than merged.  "
            "To update class-body marker regions, call merge_stubs() directly "
            "with the class-level generated content."
        )
        suffix = "" if existing.endswith("\n") else "\n"
        return existing + suffix + wrapped, warning
    return merge_stubs(existing, wrapped), None


def _has_any_marker(lines: list[str]) -> bool:
    """Return ``True`` if *lines* contains a begin or end marker."""
    return any(_is_begin(ln) or _is_end(ln) for ln in lines)


def _extract_generated_sections(generated: str) -> list[str]:
    """Return the body of each marked section in *generated*, or the whole text when unmarked."""
    lines = generated.splitlines(keepends=True)
    if not _has_any_marker(lines):
        return [generated]

    sections: list[str] = []
    body_lines: list[str] = []
    inside = False

    for line in lines:
        if _is_begin(line):
            body_lines = []
            inside = True
            continue
        if _is_end(line):
            if inside:
                sections.append("".join(body_lines))
                inside = False
            continue
        if inside:
            body_lines.append(line)

    if inside:
        sections.append("".join(body_lines))

    return sections if sections else [generated]


def _detect_indent(line: str) -> str:
    """Return the leading whitespace of *line*."""
    return line[: len(line) - len(line.lstrip())]


def _apply_indent(body: str, indent: str) -> str:
    """Prefix each non-empty, not-yet-indented line of *body* with *indent*."""
    if not indent:
        return body
    lines = []
    for line in body.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped or stripped == "\n":
            lines.append(line)
        elif line.startswith(indent):
            lines.append(line)
        else:
            lines.append(indent + stripped)
    return "".join(lines)


def _replace_marked_sections(
    existing_lines: list[str],
    generated_sections: list[str],
) -> str:
    """Replace each marked region with the next generated section, re-indenting to the marker."""
    result: list[str] = []
    gen_iter = iter(generated_sections)
    current_gen: str | None = next(gen_iter, None)

    i = 0
    lines = existing_lines
    n = len(lines)

    first_marker_idx: int | None = None
    first_is_end = False
    for idx, ln in enumerate(lines):
        if _is_begin(ln) or _is_end(ln):
            first_marker_idx = idx
            first_is_end = _is_end(ln)
            break

    if first_is_end and first_marker_idx is not None:
        result.append(BEGIN_MARKER + "\n")
        result.append(current_gen if current_gen is not None else "")
        result.append(END_MARKER + "\n")
        current_gen = next(gen_iter, current_gen)
        i = first_marker_idx + 1

    while i < n:
        line = lines[i]
        if _is_begin(line):
            indent = _detect_indent(line)
            result.append(indent + BEGIN_MARKER + "\n")
            i += 1
            found_end = False
            while i < n:
                if _is_end(lines[i]):
                    found_end = True
                    i += 1
                    break
                i += 1
            body = current_gen if current_gen is not None else ""
            result.append(_apply_indent(body, indent))
            result.append(indent + END_MARKER + "\n")
            current_gen = next(gen_iter, current_gen)
            if not found_end:
                break
        else:
            result.append(line)
            i += 1

    return "".join(result)
