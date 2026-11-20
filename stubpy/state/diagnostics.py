"""
Structured warnings and errors collected during one stub-generation run.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from ._diagnostic_types import Diagnostic, Level, Stage


@dataclass
class DiagnosticCollector:
    """Ordered accumulator of :class:`Diagnostic` records for one run.

    Every :class:`~stubpy.extend.StubContext` owns one, so pipeline stages can
    record issues without raising.

    Examples
    --------
    >>> collector = DiagnosticCollector()
    >>> collector.warning(Stage.EMIT, "Foo.bar", "No return annotation")
    >>> collector.has_warnings(), len(collector)
    (True, 1)
    """

    _items: list[Diagnostic] = field(default_factory=list)

    def add(
        self,
        level: Level,
        stage: Stage,
        symbol: str,
        message: str,
    ) -> None:
        """Append a diagnostic record.

    Parameters
    ----------
    level : Level
        Severity.
    stage : Stage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed.
    message : str
        Human-readable description.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.add(Level.INFO, Stage.LOAD, "mod", "loaded")
    >>> len(c)
    1
    """
        self._items.append(Diagnostic(level=level, stage=stage,
                                      symbol=symbol, message=message))

    def info(self, stage: Stage, symbol: str, message: str) -> None:
        """Record an INFO diagnostic.

    Parameters
    ----------
    stage : Stage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed.
    message : str
        Human-readable description.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.info(Stage.LOAD, "mod", "loaded")
    >>> c.has_info()
    True
    """
        self.add(Level.INFO, stage, symbol, message)

    def warning(self, stage: Stage, symbol: str, message: str) -> None:
        """Record a WARNING diagnostic.

    Parameters
    ----------
    stage : Stage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed.
    message : str
        Human-readable description.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.warning(Stage.RESOLVE, "Child.__init__", "unresolved **kwargs")
    >>> c.has_warnings()
    True
    """
        self.add(Level.WARNING, stage, symbol, message)

    def error(self, stage: Stage, symbol: str, message: str) -> None:
        """Record an ERROR diagnostic.

    Parameters
    ----------
    stage : Stage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed.
    message : str
        Human-readable description.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.error(Stage.LOAD, "mod", "cannot import")
    >>> c.has_errors()
    True
    """
        self.add(Level.ERROR, stage, symbol, message)

    @property
    def all(self) -> list[Diagnostic]:
        """All recorded diagnostics, in order."""
        return list(self._items)

    @property
    def info_items(self) -> list[Diagnostic]:
        """All INFO diagnostics."""
        return [d for d in self._items if d.level == Level.INFO]

    def has_info(self) -> bool:
        """Return ``True`` if any INFO diagnostic was recorded.

    Returns
    -------
    bool
        Whether at least one INFO diagnostic exists.

    Examples
    --------
    >>> DiagnosticCollector().has_info()
    False
    """
        return any(d.level == Level.INFO for d in self._items)

    @property
    def warnings(self) -> list[Diagnostic]:
        """All WARNING diagnostics."""
        return [d for d in self._items if d.level == Level.WARNING]

    @property
    def errors(self) -> list[Diagnostic]:
        """All ERROR diagnostics."""
        return [d for d in self._items if d.level == Level.ERROR]

    @property
    def infos(self) -> list[Diagnostic]:
        """All INFO diagnostics."""
        return [d for d in self._items if d.level == Level.INFO]

    def has_errors(self) -> bool:
        """Return ``True`` if any ERROR diagnostic was recorded.

    Returns
    -------
    bool
        Whether at least one ERROR diagnostic exists.

    Examples
    --------
    >>> DiagnosticCollector().has_errors()
    False
    """
        return any(d.level == Level.ERROR for d in self._items)

    def has_warnings(self) -> bool:
        """Return ``True`` if any WARNING diagnostic was recorded.

    Returns
    -------
    bool
        Whether at least one WARNING diagnostic exists.

    Examples
    --------
    >>> DiagnosticCollector().has_warnings()
    False
    """
        return any(d.level == Level.WARNING for d in self._items)

    def by_stage(self, stage: Stage) -> list[Diagnostic]:
        """Return all diagnostics from *stage*.

    Parameters
    ----------
    stage : Stage
        The stage to select.

    Returns
    -------
    list of Diagnostic
        The matching diagnostics, in order.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.warning(Stage.EMIT, "f", "no return annotation")
    >>> len(c.by_stage(Stage.EMIT)), len(c.by_stage(Stage.LOAD))
    (1, 0)
    """
        return [d for d in self._items if d.stage == stage]

    def by_symbol(self, symbol: str) -> list[Diagnostic]:
        """Return all diagnostics recorded for *symbol*.

    Parameters
    ----------
    symbol : str
        The symbol name, exactly as recorded.

    Returns
    -------
    list of Diagnostic
        The matching diagnostics, in order.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.warning(Stage.EMIT, "f", "no return annotation")
    >>> [d.message for d in c.by_symbol("f")]
    ['no return annotation']
    """
        return [d for d in self._items if d.symbol == symbol]

    def summary(self) -> str:
        """Return a one-line count summary, e.g. ``'0 errors, 0 warnings, 0 infos'``.

    Returns
    -------
    str
        The number of errors, warnings and infos.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.error(Stage.LOAD, "mod", "cannot import")
    >>> c.summary()
    '1 errors, 0 warnings, 0 infos'
    """
        e = sum(1 for d in self._items if d.level == Level.ERROR)
        w = sum(1 for d in self._items if d.level == Level.WARNING)
        i = sum(1 for d in self._items if d.level == Level.INFO)
        return f"{e} errors, {w} warnings, {i} infos"

    def format_all(self) -> str:
        """Return all diagnostics joined by newlines.

    Returns
    -------
    str
        One ``str(diagnostic)`` line per record; empty when there are none.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.info(Stage.LOAD, "mod", "loaded")
    >>> print(c.format_all())
    [INFO] (load) mod: loaded
    """
        return "\n".join(str(d) for d in self._items)

    def clear(self) -> None:
        """Remove all recorded diagnostics.

    Examples
    --------
    >>> c = DiagnosticCollector()
    >>> c.info(Stage.LOAD, "mod", "loaded")
    >>> c.clear()
    >>> len(c)
    0
    """
        self._items.clear()

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)
