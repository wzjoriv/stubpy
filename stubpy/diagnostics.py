"""
stubpy.diagnostics
==================

Structured warning/error accumulation for a single stub-generation pass.

Replaces the bare ``try/except pass`` blocks scattered through the pipeline
with a collector that records every issue, preserving full context for
debugging without silently discarding information.

Every pipeline stage is given a :attr:`DiagnosticStage` value so that the
origin of a problem is always traceable.  The :class:`DiagnosticCollector`
held by :class:`~stubpy.context.StubContext` accumulates all diagnostics
for the run; callers can inspect :attr:`~DiagnosticCollector.errors` and
:attr:`~DiagnosticCollector.warnings` to decide how to proceed.

Usage example
-------------

.. code-block:: python

    from stubpy.diagnostics import DiagnosticCollector, DiagnosticLevel, DiagnosticStage

    collector = DiagnosticCollector()
    collector.warning(DiagnosticStage.RESOLVE, "MyClass.__init__",
                      "Could not resolve **kwargs — parent not found in MRO")

    for diag in collector:
        print(diag)
    # [WARNING] (resolve) MyClass.__init__: Could not resolve ...

    if collector.has_errors():
        raise RuntimeError("Stub generation failed with errors")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DiagnosticLevel(Enum):
    """Severity of a single diagnostic message."""
    INFO    = "INFO"
    WARNING = "WARNING"
    ERROR   = "ERROR"


class DiagnosticStage(Enum):
    """
    Pipeline stage that produced a diagnostic.

    Matches the stages described in the architecture document so that a
    diagnostic message can be traced to its origin without reading source.
    """
    LOAD         = "load"
    AST_PASS     = "ast_pass"
    SYMBOL_TABLE = "symbol_table"
    ALIAS        = "alias"
    RESOLVE      = "resolve"
    EMIT         = "emit"
    IMPORT       = "import"
    GENERATOR    = "generator"


# ---------------------------------------------------------------------------
# Diagnostic record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Diagnostic:
    """
    An immutable record of a single issue detected during stub generation.

    Parameters
    ----------
    level : DiagnosticLevel
        Severity.
    stage : DiagnosticStage
        Pipeline stage that raised this diagnostic.
    symbol : str
        Human-readable name of the symbol being processed when the issue
        was detected (e.g. ``"MyClass.__init__"`` or ``"module-level"``).
    message : str
        Human-readable description of the issue.

    Examples
    --------
    >>> from stubpy.diagnostics import Diagnostic, DiagnosticLevel, DiagnosticStage
    >>> d = Diagnostic(DiagnosticLevel.WARNING, DiagnosticStage.RESOLVE,
    ...                "Child.__init__", "Could not resolve kwargs")
    >>> str(d)
    '[WARNING] (resolve) Child.__init__: Could not resolve kwargs'
    """
    level:   DiagnosticLevel
    stage:   DiagnosticStage
    symbol:  str
    message: str

    def __str__(self) -> str:
        return (
            f"[{self.level.value}] ({self.stage.value})"
            f" {self.symbol}: {self.message}"
        )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

@dataclass
class DiagnosticCollector:
    """
    Mutable accumulator for :class:`Diagnostic` records produced during
    one stub-generation run.

    A fresh instance is created inside every :class:`~stubpy.context.StubContext`
    and passed through the pipeline so every stage can record issues without
    raising exceptions.

    Attributes
    ----------
    _items : list of Diagnostic
        Internal ordered list. Use the public properties to access it.

    Examples
    --------
    >>> collector = DiagnosticCollector()
    >>> collector.warning(DiagnosticStage.EMIT, "Foo.bar", "No return annotation")
    >>> collector.has_warnings()
    True
    >>> len(collector)
    1
    """

    _items: list[Diagnostic] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def add(
        self,
        level:   DiagnosticLevel,
        stage:   DiagnosticStage,
        symbol:  str,
        message: str,
    ) -> None:
        """
        Append a diagnostic record.

        Parameters
        ----------
        level : DiagnosticLevel
        stage : DiagnosticStage
        symbol : str
        message : str
        """
        self._items.append(Diagnostic(level=level, stage=stage,
                                      symbol=symbol, message=message))

    def info(
        self, stage: DiagnosticStage, symbol: str, message: str
    ) -> None:
        """Convenience wrapper — records an :attr:`~DiagnosticLevel.INFO` diagnostic."""
        self.add(DiagnosticLevel.INFO, stage, symbol, message)

    def warning(
        self, stage: DiagnosticStage, symbol: str, message: str
    ) -> None:
        """Convenience wrapper — records a :attr:`~DiagnosticLevel.WARNING` diagnostic."""
        self.add(DiagnosticLevel.WARNING, stage, symbol, message)

    def error(
        self, stage: DiagnosticStage, symbol: str, message: str
    ) -> None:
        """Convenience wrapper — records an :attr:`~DiagnosticLevel.ERROR` diagnostic."""
        self.add(DiagnosticLevel.ERROR, stage, symbol, message)

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    @property
    def all(self) -> list[Diagnostic]:
        """Return a copy of all recorded diagnostics in order."""
        return list(self._items)

    @property
    def warnings(self) -> list[Diagnostic]:
        """Return all :attr:`~DiagnosticLevel.WARNING` diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.WARNING]

    @property
    def errors(self) -> list[Diagnostic]:
        """Return all :attr:`~DiagnosticLevel.ERROR` diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.ERROR]

    @property
    def infos(self) -> list[Diagnostic]:
        """Return all :attr:`~DiagnosticLevel.INFO` diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.INFO]

    def has_errors(self) -> bool:
        """Return ``True`` if any :attr:`~DiagnosticLevel.ERROR` was recorded."""
        return any(d.level == DiagnosticLevel.ERROR for d in self._items)

    def has_warnings(self) -> bool:
        """Return ``True`` if any :attr:`~DiagnosticLevel.WARNING` was recorded."""
        return any(d.level == DiagnosticLevel.WARNING for d in self._items)

    def by_stage(self, stage: DiagnosticStage) -> list[Diagnostic]:
        """Return all diagnostics from *stage*."""
        return [d for d in self._items if d.stage == stage]

    def by_symbol(self, symbol: str) -> list[Diagnostic]:
        """Return all diagnostics whose ``symbol`` field equals *symbol*."""
        return [d for d in self._items if d.symbol == symbol]

    def summary(self) -> str:
        """
        Return a human-readable summary line.

        Examples
        --------
        >>> c = DiagnosticCollector()
        >>> c.summary()
        '0 errors, 0 warnings, 0 infos'
        """
        e = sum(1 for d in self._items if d.level == DiagnosticLevel.ERROR)
        w = sum(1 for d in self._items if d.level == DiagnosticLevel.WARNING)
        i = sum(1 for d in self._items if d.level == DiagnosticLevel.INFO)
        return f"{e} errors, {w} warnings, {i} infos"

    def format_all(self) -> str:
        """Return all diagnostics joined by newlines, suitable for printing."""
        return "\n".join(str(d) for d in self._items)

    def clear(self) -> None:
        """Remove all recorded diagnostics."""
        self._items.clear()

    # ------------------------------------------------------------------
    # Python protocol
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        """``True`` when the collector is non-empty."""
        return bool(self._items)
