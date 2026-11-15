"""Structured warnings and errors collected during one stub-generation run."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum, IntEnum


class DiagnosticLevel(IntEnum):
    """Severity of a diagnostic; levels compare with ``<`` / ``>=``."""
    INFO = 10
    WARNING = 20
    ERROR = 30


class DiagnosticStage(Enum):
    """Pipeline stage that produced a diagnostic."""
    LOAD = "load"
    AST_PASS = "ast_pass"
    SYMBOL_TABLE = "symbol_table"
    ALIAS = "alias"
    RESOLVE = "resolve"
    EMIT = "emit"
    IMPORT = "import"
    GENERATOR = "generator"


@dataclass(frozen=True)
class Diagnostic:
    """An immutable record of one issue detected during stub generation.

    Parameters
    ----------
    level : DiagnosticLevel
        Severity.
    stage : DiagnosticStage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed, e.g. ``"MyClass.__init__"``.
    message : str
        Human-readable description.

    Examples
    --------
    >>> d = Diagnostic(DiagnosticLevel.WARNING, DiagnosticStage.RESOLVE,
    ...                "Child.__init__", "Could not resolve kwargs")
    >>> str(d)
    '[WARNING] (resolve) Child.__init__: Could not resolve kwargs'
    """
    level: DiagnosticLevel
    stage: DiagnosticStage
    symbol: str
    message: str

    def __str__(self) -> str:
        return (
            f"[{self.level.name}] ({self.stage.value})"
            f" {self.symbol}: {self.message}"
        )


@dataclass
class DiagnosticCollector:
    """Ordered accumulator of :class:`Diagnostic` records for one run.

    Every :class:`~stubpy.StubContext` owns one, so pipeline stages can
    record issues without raising.

    Examples
    --------
    >>> collector = DiagnosticCollector()
    >>> collector.warning(DiagnosticStage.EMIT, "Foo.bar", "No return annotation")
    >>> collector.has_warnings(), len(collector)
    (True, 1)
    """

    _items: list[Diagnostic] = field(default_factory=list)

    def add(
        self,
        level: DiagnosticLevel,
        stage: DiagnosticStage,
        symbol: str,
        message: str,
    ) -> None:
        """Append a diagnostic record."""
        self._items.append(Diagnostic(level=level, stage=stage,
                                      symbol=symbol, message=message))

    def info(self, stage: DiagnosticStage, symbol: str, message: str) -> None:
        """Record an INFO diagnostic."""
        self.add(DiagnosticLevel.INFO, stage, symbol, message)

    def warning(self, stage: DiagnosticStage, symbol: str, message: str) -> None:
        """Record a WARNING diagnostic."""
        self.add(DiagnosticLevel.WARNING, stage, symbol, message)

    def error(self, stage: DiagnosticStage, symbol: str, message: str) -> None:
        """Record an ERROR diagnostic."""
        self.add(DiagnosticLevel.ERROR, stage, symbol, message)

    @property
    def all(self) -> list[Diagnostic]:
        """All recorded diagnostics, in order."""
        return list(self._items)

    @property
    def info_items(self) -> list[Diagnostic]:
        """All INFO diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.INFO]

    def has_info(self) -> bool:
        """Return ``True`` if any INFO diagnostic was recorded."""
        return any(d.level == DiagnosticLevel.INFO for d in self._items)

    @property
    def warnings(self) -> list[Diagnostic]:
        """All WARNING diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.WARNING]

    @property
    def errors(self) -> list[Diagnostic]:
        """All ERROR diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.ERROR]

    @property
    def infos(self) -> list[Diagnostic]:
        """All INFO diagnostics."""
        return [d for d in self._items if d.level == DiagnosticLevel.INFO]

    def has_errors(self) -> bool:
        """Return ``True`` if any ERROR diagnostic was recorded."""
        return any(d.level == DiagnosticLevel.ERROR for d in self._items)

    def has_warnings(self) -> bool:
        """Return ``True`` if any WARNING diagnostic was recorded."""
        return any(d.level == DiagnosticLevel.WARNING for d in self._items)

    def by_stage(self, stage: DiagnosticStage) -> list[Diagnostic]:
        """Return all diagnostics from *stage*."""
        return [d for d in self._items if d.stage == stage]

    def by_symbol(self, symbol: str) -> list[Diagnostic]:
        """Return all diagnostics recorded for *symbol*."""
        return [d for d in self._items if d.symbol == symbol]

    def summary(self) -> str:
        """Return a one-line count summary, e.g. ``'0 errors, 0 warnings, 0 infos'``."""
        e = sum(1 for d in self._items if d.level == DiagnosticLevel.ERROR)
        w = sum(1 for d in self._items if d.level == DiagnosticLevel.WARNING)
        i = sum(1 for d in self._items if d.level == DiagnosticLevel.INFO)
        return f"{e} errors, {w} warnings, {i} infos"

    def format_all(self) -> str:
        """Return all diagnostics joined by newlines."""
        return "\n".join(str(d) for d in self._items)

    def clear(self) -> None:
        """Remove all recorded diagnostics."""
        self._items.clear()

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)
