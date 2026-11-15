"""Result type returned by :func:`~stubpy.generate_package`."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .diagnostics import Diagnostic


@dataclass
class PackageResult:
    """Outcome of a :func:`~stubpy.generate_package` run.

    Attributes
    ----------
    stubs_written : list of Path
        Every ``.pyi`` file successfully written.
    failed : list of tuple[Path, list[Diagnostic]]
        ``(source_path, error_diagnostics)`` for each file that raised or
        recorded ERROR diagnostics.

    Examples
    --------
    >>> PackageResult().summary()
    'Generated 0 stubs, 0 failed.'
    """
    stubs_written: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, list[Diagnostic]]] = field(default_factory=list)

    def summary(self) -> str:
        """Return a one-line summary such as ``'Generated 1 stub, 0 failed.'``."""
        n = len(self.stubs_written)
        noun = "stub" if n == 1 else "stubs"
        return f"Generated {n} {noun}, {len(self.failed)} failed."
