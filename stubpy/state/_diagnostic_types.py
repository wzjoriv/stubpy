"""
Severity levels, pipeline stages and the single :class:`Diagnostic` record.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Level(IntEnum):
    """Severity of a :class:`Diagnostic`.

    Levels are ordered, so ``d.level >= Level.WARNING`` selects warnings
    and errors.

    Attributes
    ----------
    INFO
        Progress notes, shown with ``verbose``.
    WARNING
        Something was approximated (for example an unresolvable
        ``**kwargs``); the stub is still usable.  A failure under ``strict``.
    ERROR
        The module could not be stubbed; its :class:`~stubpy.StubResult` is
        not ``ok``.

    Examples
    --------
    >>> Level.ERROR > Level.WARNING
    True
    """
    INFO = 10
    WARNING = 20
    ERROR = 30


class Stage(Enum):
    """Pipeline stage that produced a :class:`Diagnostic`.

    Attributes
    ----------
    LOAD, AST_PASS, SYMBOL_TABLE, ALIAS, RESOLVE, EMIT, IMPORT, GENERATOR, TYPECHECK
        Loading the module, the AST pre-pass, building the symbol table,
        alias detection, ``**kwargs`` / ``*args`` resolution, stub emission,
        import assembly, run-level steps such as writing and merging, and
        type-checking the written stubs (``typecheck``).

    Examples
    --------
    >>> Stage.RESOLVE.value
    'resolve'
    """
    LOAD = "load"
    AST_PASS = "ast_pass"
    SYMBOL_TABLE = "symbol_table"
    ALIAS = "alias"
    RESOLVE = "resolve"
    EMIT = "emit"
    IMPORT = "import"
    GENERATOR = "generator"
    TYPECHECK = "typecheck"


@dataclass(frozen=True)
class Diagnostic:
    """An immutable record of one issue detected during stub generation.

    ``str(diagnostic)`` gives ``[LEVEL] (stage) symbol: message``.

    Parameters
    ----------
    level : Level
        Severity.
    stage : Stage
        Pipeline stage that raised it.
    symbol : str
        Name of the symbol being processed, e.g. ``"MyClass.__init__"``.
    message : str
        Human-readable description.

    See Also
    --------
    DiagnosticCollector : Accumulates diagnostics during a run.

    Examples
    --------
    >>> d = Diagnostic(Level.WARNING, Stage.RESOLVE,
    ...                "Child.__init__", "Could not resolve kwargs")
    >>> str(d)
    '[WARNING] (resolve) Child.__init__: Could not resolve kwargs'
    """
    level: Level
    stage: Stage
    symbol: str
    message: str

    def __str__(self) -> str:
        return (
            f"[{self.level.name}] ({self.stage.value})"
            f" {self.symbol}: {self.message}"
        )
