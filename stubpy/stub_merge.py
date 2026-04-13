"""
stubpy.stub_merge
=================

Incremental stub update — merge newly generated stubs with an existing
``.pyi`` file while preserving manually edited content.

The merge system wraps auto-generated sections with marker comments::

    # stubpy: auto-generated begin
    ... (generated content) ...
    # stubpy: auto-generated end

On subsequent runs only the content *between* the markers is replaced.
Content outside the markers (manual additions, hand-tuned overloads, etc.)
is preserved unchanged.

Marker rules
------------
- **Case-insensitive** and **whitespace-lenient**: ``# Stubpy : Auto-Generated Begin``
  and ``#stubpy:auto-generated begin`` are both valid.
- **Multiple pairs** in one file are supported.  Each ``begin``/``end`` pair
  is replaced independently.
- **Half-open markers** are handled gracefully:
  - An ``end`` without a preceding ``begin`` → the start of the file is
    treated as the implicit ``begin`` (the generated header replaced).
  - A ``begin`` without a following ``end`` → the end of the file is
    treated as the implicit ``end`` (everything after the begin replaced).
- Content outside *all* marker pairs is left untouched.

The markers are added to new stubs automatically by :func:`wrap_generated`.
When merging into an existing file that has no markers at all, the entire
existing file content is left unchanged and the new content is appended
inside a fresh marker pair — giving the developer a chance to review the
difference before committing.

Public API
----------
:func:`wrap_generated`
    Wrap a newly generated stub body with ``begin``/``end`` markers.
:func:`merge_stubs`
    Merge a freshly generated stub into an existing ``.pyi`` file.
"""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Marker recognition
# ---------------------------------------------------------------------------

#: Canonical form written into new stubs.
BEGIN_MARKER = "# stubpy: auto-generated begin"
END_MARKER   = "# stubpy: auto-generated end"

# Pattern that matches any reasonable spelling of a begin / end marker.
# Tolerates: extra spaces, any capitalisation, colon vs no colon, hyphen vs space.
_BEGIN_RE = re.compile(
    r"^\s*#\s*stubpy\s*:?\s*auto[-\s]?generated\s*begin\s*$",
    re.IGNORECASE,
)
_END_RE = re.compile(
    r"^\s*#\s*stubpy\s*:?\s*auto[-\s]?generated\s*end\s*$",
    re.IGNORECASE,
)


def _is_begin(line: str) -> bool:
    """Return ``True`` if *line* is a begin marker (case/space insensitive)."""
    return bool(_BEGIN_RE.match(line.rstrip("\n")))


def _is_end(line: str) -> bool:
    """Return ``True`` if *line* is an end marker (case/space insensitive)."""
    return bool(_END_RE.match(line.rstrip("\n")))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def wrap_generated(content: str) -> str:
    """Wrap *content* between canonical begin/end markers.

    The markers are added exactly once — they are not added again if
    *content* already contains them.

    Parameters
    ----------
    content : str
        A complete stub file string, typically the output of
        :func:`~stubpy.generator.generate_stub`.

    Returns
    -------
    str
        *content* with ``# stubpy: auto-generated begin`` prepended and
        ``# stubpy: auto-generated end`` appended (with trailing newline).

    Examples
    --------
    >>> wrapped = wrap_generated("x: int\\n")
    >>> wrapped.startswith("# stubpy: auto-generated begin")
    True
    >>> wrapped.strip().endswith("# stubpy: auto-generated end")
    True
    """
    # Don't double-wrap
    if any(_is_begin(ln) for ln in content.splitlines()):
        return content

    lines = [BEGIN_MARKER + "\n", content]
    if not content.endswith("\n"):
        lines.append("\n")
    lines.append(END_MARKER + "\n")
    return "".join(lines)


def merge_stubs(existing: str, generated: str) -> str:
    """Merge *generated* stub content into *existing* ``.pyi`` content.

    Only the regions inside marker pairs are replaced.  Everything
    outside the markers is left untouched.

    Strategy when no markers exist in *existing*
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The entire existing file is left as-is and the new content is appended
    as a new marked section.  This is intentionally conservative — on the
    *first* run after adding markers the developer reviews the diff.

    Parameters
    ----------
    existing : str
        Current content of the ``.pyi`` file on disk.
    generated : str
        Freshly generated stub content (already passed through
        :func:`wrap_generated`).

    Returns
    -------
    str
        Merged content suitable for writing back to disk.

    Examples
    --------
    >>> existing = (
    ...     "# manual stuff\\n"
    ...     "# stubpy: auto-generated begin\\n"
    ...     "x: int\\n"
    ...     "# stubpy: auto-generated end\\n"
    ...     "# more manual\\n"
    ... )
    >>> generated = "# stubpy: auto-generated begin\\ny: str\\n# stubpy: auto-generated end\\n"
    >>> result = merge_stubs(existing, generated)
    >>> "y: str" in result
    True
    >>> "# manual stuff" in result
    True
    >>> "# more manual" in result
    True
    >>> "x: int" not in result
    True
    """
    existing_lines = existing.splitlines(keepends=True)
    generated_sections = _extract_generated_sections(generated)

    if not _has_any_marker(existing_lines):
        # No markers at all — conservative: append new section
        suffix = "" if existing.endswith("\n") else "\n"
        return existing + suffix + wrap_generated(generated)

    return _replace_marked_sections(existing_lines, generated_sections)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_any_marker(lines: list[str]) -> bool:
    """Return True if *lines* contains at least one begin or end marker."""
    return any(_is_begin(ln) or _is_end(ln) for ln in lines)


def _extract_generated_sections(generated: str) -> list[str]:
    """Extract the body texts from all marked sections in *generated*.

    Returns a list of body strings (one per ``begin``/``end`` pair).
    If *generated* has no markers the entire text is treated as one section.
    """
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

    # Half-open: begin without matching end → rest of file is the body
    if inside:
        sections.append("".join(body_lines))

    return sections if sections else [generated]


def _detect_indent(line: str) -> str:
    """Return the leading whitespace of *line* (used for indentation-aware merge)."""
    return line[: len(line) - len(line.lstrip())]


def _apply_indent(body: str, indent: str) -> str:
    """Prefix every non-empty line of *body* with *indent*.

    Empty lines and lines that already start with *indent* are left unchanged.
    This allows markers placed inside class or method bodies to preserve the
    surrounding indentation context.
    """
    if not indent:
        return body
    lines = []
    for line in body.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped or stripped == "\n":
            lines.append(line)
        elif line.startswith(indent):
            lines.append(line)  # already indented correctly
        else:
            lines.append(indent + stripped)
    return "".join(lines)


def _replace_marked_sections(
    existing_lines: list[str],
    generated_sections: list[str],
) -> str:
    """Replace each ``begin``/``end`` pair in *existing_lines* with the
    next body from *generated_sections*, cycling if fewer sections than pairs.

    **Indentation-aware**: when a begin marker has leading whitespace (e.g. it
    is placed inside a class body), the generated content is re-indented to
    match so the result remains syntactically valid.

    Half-open handling:
    - End without begin → treat file-start as implicit begin.
    - Begin without end → treat file-end as implicit end.
    """
    result: list[str] = []
    gen_iter = iter(generated_sections)
    current_gen: str | None = next(gen_iter, None)

    i = 0
    lines = existing_lines
    n = len(lines)

    # If the very first marker is an END (no preceding begin), treat it as
    # if the file started with a begin marker — replace from line 0.
    first_marker_idx: int | None = None
    first_is_end = False
    for idx, ln in enumerate(lines):
        if _is_begin(ln) or _is_end(ln):
            first_marker_idx = idx
            first_is_end = _is_end(ln)
            break

    if first_is_end and first_marker_idx is not None:
        body = current_gen if current_gen is not None else ""
        result.append(BEGIN_MARKER + "\n")
        result.append(body)
        result.append(END_MARKER + "\n")
        current_gen = next(gen_iter, current_gen)
        i = first_marker_idx + 1

    while i < n:
        line = lines[i]
        if _is_begin(line):
            # Detect indentation from the begin-marker line itself
            indent = _detect_indent(line)
            result.append(indent + BEGIN_MARKER + "\n")
            # Consume lines until END (or EOF)
            i += 1
            found_end = False
            while i < n:
                if _is_end(lines[i]):
                    found_end = True
                    i += 1
                    break
                i += 1
            # Inject new content, re-indented to match context
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


def read_and_merge(output_path: Path, generated: str) -> str:
    """Read *output_path* (if it exists) and merge *generated* into it.

    Parameters
    ----------
    output_path : Path
        Path to the existing ``.pyi`` file.  When the file does not exist,
        *generated* (wrapped in markers) is returned directly.
    generated : str
        Freshly generated stub content from :func:`~stubpy.generator.generate_stub`.

    Returns
    -------
    str
        Final merged content ready to be written to *output_path*.
    """
    wrapped = wrap_generated(generated)
    if not output_path.exists():
        return wrapped
    existing = output_path.read_text(encoding="utf-8")
    return merge_stubs(existing, wrapped)
