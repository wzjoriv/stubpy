"""
Result types: :class:`StubResult` for one module and :class:`Report` for a run.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from stubpy.core._constants import IMPORT_BLOCKED_PREFIX, IMPORT_FAILED_PREFIX
from stubpy.state.diagnostics import Diagnostic, Level, Stage


@dataclass(frozen=True)
class StubResult:
    """The stub of one module and what happened while building it.

    Returned by :func:`~stubpy.render`; :func:`~stubpy.generate` and
    :func:`~stubpy.check` collect one per module in a :class:`Report`.

    Parameters
    ----------
    text : str
        The stub text.  For :func:`~stubpy.generate` and :func:`~stubpy.check`
        this is the full file content, merged into the existing stub when
        ``incremental`` is on; empty when generation failed.
    diagnostics : tuple of Diagnostic, optional
        Everything recorded while building the stub, in order.  Defaults to ``()``.
    source : pathlib.Path or None, optional
        The ``.py`` file (or package folder, for a placeholder
        ``__init__.pyi``) the stub was built from.  Defaults to ``None``.
    module_name : str, optional
        The module's dotted name; loose scripts get a synthetic one.
        Defaults to ``""``.
    output : pathlib.Path or None, optional
        Where the stub is (or would be) written; ``None`` for
        :func:`~stubpy.render`.  Defaults to ``None``.

    See Also
    --------
    Report : The outcome of a whole run.

    Examples
    --------
    >>> result = StubResult("x: int\\n", module_name="mod")
    >>> result.ok, result.errors, result.warnings
    (True, [], [])
    """
    text: str
    diagnostics: tuple[Diagnostic, ...] = ()
    source: Path | None = None
    module_name: str = ""
    output: Path | None = None

    @property
    def ok(self) -> bool:
        """``True`` when no ERROR diagnostic was recorded."""
        return not any(d.level is Level.ERROR for d in self.diagnostics)

    @property
    def errors(self) -> list[Diagnostic]:
        """The ERROR diagnostics."""
        return [d for d in self.diagnostics if d.level is Level.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        """The WARNING diagnostics."""
        return [d for d in self.diagnostics if d.level is Level.WARNING]

    @property
    def import_failures(self) -> list[Diagnostic]:
        """The WARNINGs saying the module could not be imported and was stubbed from its source."""
        return [
            d for d in self.diagnostics
            if d.stage is Stage.LOAD and d.level is Level.WARNING and d.message.startswith(IMPORT_FAILED_PREFIX)
        ]

    @property
    def import_blocked(self) -> bool:
        """``True`` when the import policy kept the module from being imported."""
        return any(d.stage is Stage.LOAD and d.message.startswith(IMPORT_BLOCKED_PREFIX) for d in self.diagnostics)


@dataclass
class Report:
    """The outcome of :func:`~stubpy.generate` or :func:`~stubpy.check`.

    Iterating a report yields its :class:`StubResult` objects.  A run builds
    one itself; the fields are listed so a report can be read or constructed.

    Parameters
    ----------
    results : list of StubResult, optional
        One per module, in processing order.  Defaults to an empty list.
    written : list of pathlib.Path, optional
        Stubs written to disk (always empty for ``check``).  Defaults to an
        empty list.
    stale : list of pathlib.Path, optional
        Stubs on disk that differ from what would be generated, or are
        missing (``check`` only).  Defaults to an empty list.
    excluded : list of tuple of (pathlib.Path, str), optional
        Files a folder target skipped and the ``exclude`` pattern that
        matched; never counted as failures.  Defaults to an empty list.
    action : str, optional
        ``"generate"`` or ``"check"``.  Defaults to ``"generate"``.
    strict : bool, optional
        Count results with WARNING diagnostics as failed.  Defaults to ``False``.
    type_errors : int, optional
        Errors the type checker found in the stubs (``typecheck``).  Defaults to 0.
    typecheck_note : str, optional
        Why the type check did not run, if it was asked for and did not.  Defaults to ``""``.

    See Also
    --------
    StubResult : The stub of one module.

    Examples
    --------
    >>> report = Report(results=[StubResult("x: int\\n")], action="check")
    >>> report.ok, len(report)
    (True, 1)
    >>> report.summary()
    'Checked 1 stub: 0 stale, 0 failed.'
    >>> from stubpy.state.diagnostics import Diagnostic, Level, Stage
    >>> broken = Diagnostic(Level.WARNING, Stage.LOAD, "m.py", "Import failed, falling back to source analysis: E")
    >>> Report(results=[StubResult("x: int", (broken,))], written=[Path("m.pyi")]).summary()
    'Generated 1 stub, 0 failed. 1 module stubbed from source only: import failed.'
    """
    results: list[StubResult] = field(default_factory=list)
    written: list[Path] = field(default_factory=list)
    stale: list[Path] = field(default_factory=list)
    excluded: list[tuple[Path, str]] = field(default_factory=list)
    action: str = "generate"
    strict: bool = False
    type_errors: int = 0
    typecheck_note: str = ""

    @property
    def failed(self) -> list[StubResult]:
        """Results with ERROR diagnostics (or WARNINGs in strict mode)."""
        return [r for r in self.results if not r.ok or (self.strict and r.warnings)]

    @property
    def ok(self) -> bool:
        """``True`` when nothing failed and nothing is stale."""
        return not self.failed and not self.stale

    def summary(self) -> str:
        """Return a one-line summary, e.g. ``'Generated 3 stubs, 0 failed.'``.

    Returns
    -------
    str
        For ``generate``, the number of stubs written and failed; for
        ``check``, the number checked, stale and failed.  Modules stubbed
        from source only because their import failed, or the import policy
        blocked it, are counted after.

    Examples
    --------
    >>> Report().summary()
    'Generated 0 stubs, 0 failed.'
    >>> Report(action="check").summary()
    'Checked 0 stubs: 0 stale, 0 failed.'
    """
        n_failed = len(self.failed)
        if self.action == "check":
            n = len(self.results)
            line = f"Checked {n} {_stubs(n)}: {len(self.stale)} stale, {n_failed} failed."
        else:
            n = len(self.written)
            line = f"Generated {n} {_stubs(n)}, {n_failed} failed."
        line += _source_only(self.results)
        if self.type_errors:
            line += f" {self.type_errors} type {'error' if self.type_errors == 1 else 'errors'} in the stubs."
        return line + (f" ({self.typecheck_note})" if self.typecheck_note else "")

    def __iter__(self) -> Iterator[StubResult]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


def _stubs(n: int) -> str:
    return "stub" if n == 1 else "stubs"


def _source_only(results: list[StubResult]) -> str:
    """The summary sentences counting modules stubbed from source because their import failed or was blocked."""
    failed = sum(bool(r.import_failures) for r in results)
    blocked = sum(r.import_blocked for r in results)
    parts = [f" {n} {'module' if n == 1 else 'modules'} stubbed from source only: {why}."
             for n, why in ((failed, "import failed"), (blocked, "import blocked by the import policy")) if n]
    return "".join(parts)
