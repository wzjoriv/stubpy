"""
Turning a rendered stub into its file: kept hand-written stubs, merges, placeholders and atomic writes.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from stubpy.analysis.loader import find_import_target
from stubpy.compiled.detect import is_extension_file
from stubpy.config.options import Config
from stubpy.core._constants import INIT_PYI_PLACEHOLDER, STUB_EOL_PROBE
from stubpy.merge import read_and_merge

from .diagnostics import Diagnostic, Level, Stage
from .results import Report, StubResult
from .targets import Job


def _keeps_handwritten(job: Job, output: str | os.PathLike[str] | None, cfg: Config) -> bool:
    """True for an extension module whose stub already sits next to it and nothing asked to replace it."""
    return output is None and not cfg.incremental and (is_extension_file(job.source) or job.source.suffix == ".pyx") \
        and job.output.is_file()


def _kept(job: Job) -> StubResult:
    """The result for an existing stub left untouched: no output, so it is neither written nor compared."""
    note = Diagnostic(Level.INFO, Stage.GENERATOR, job.source.name,
                      f"Kept the existing {job.output.name}; use an output folder or --incremental to regenerate it, "
                      "or 'stubpy docstrings sync' to refresh its docstrings")
    return StubResult("", (note,), job.source, _dotted_name(job.source), None)


def _merged(result: StubResult, cfg: Config) -> StubResult:
    """Return *result* with its text merged into the existing stub when ``incremental`` is on.

    A stub that cannot be merged safely gets an ERROR and is not written; one
    without markers is left alone (no output) with a WARNING.
    """
    if not cfg.incremental or not result.ok or result.output is None:
        return result
    merged = read_and_merge(result.output, result.text)
    name = result.source.name if result.source else ""
    levels = {"info": Level.INFO, "warning": Level.WARNING, "error": Level.ERROR}
    notes = tuple(Diagnostic(levels[n.level], Stage.GENERATOR, name, n.message) for n in merged.notes)
    if merged.text is None:
        return replace(result, text="", output=result.output if not merged.ok else None,
                       diagnostics=(*result.diagnostics, *notes))
    return replace(result, text=merged.text, diagnostics=(*result.diagnostics, *notes))


def _placeholder(job: Job) -> StubResult:
    """Return the result for a package folder's placeholder ``__init__.pyi``."""
    return StubResult(INIT_PYI_PLACEHOLDER, (), job.source, _dotted_name(job.source / "__init__.py"), job.output)


def _finish(result: StubResult, report: Report, raw: bool = False) -> None:
    """Record *result* and write its stub (``generate``) or compare it with the file on disk (``check``).

    *raw* text (an incremental merge) keeps its own line endings; other text
    is written with the platform's.
    """
    report.results.append(result)
    if not result.ok or result.output is None:
        return
    if report.action == "check":
        existing = None
        if result.output.is_file():
            existing = result.output.read_bytes().decode("utf-8", "replace") if raw else                 result.output.read_text(encoding="utf-8")
        if existing != result.text:
            report.stale.append(result.output)
        return
    write_atomic(result.output, result.text, raw)
    report.written.append(result.output)


def write_atomic(path: Path, text: str, raw: bool = False) -> None:
    """Write *text* to a temporary file beside *path*, then replace *path* with it.

    Missing parent folders are created, and the temporary file is removed if
    the write fails.

    Parameters
    ----------
    path : pathlib.Path
        The file to write.
    text : str
        The content, UTF-8 encoded.
    raw : bool, optional
        Write line endings exactly as they are in *text*.  Otherwise ``\\n`` is
        written, or ``\\r\\n`` when the file being replaced already uses it.
        Defaults to ``False``.

    Raises
    ------
    OSError
        If the file cannot be written or replaced.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     target = pathlib.Path(folder) / "pkg" / "m.pyi"
    ...     write_atomic(target, "x: int\\n")
    ...     target.read_text(encoding="utf-8")
    'x: int\\n'
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    newline = "" if raw else _line_ending(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _line_ending(path: Path) -> str:
    """``\\r\\n`` when the existing file at *path* uses it, else ``\\n``."""
    try:
        with path.open("rb") as fh:
            return "\r\n" if b"\r\n" in fh.read(STUB_EOL_PROBE) else "\n"
    except OSError:
        return "\n"


def _dotted_name(path: Path) -> str:
    target = find_import_target(path)
    return target.name if target is not None else path.stem
