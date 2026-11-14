"""Pipeline core: run context, diagnostics, results, and the generate_* orchestration.

The orchestration modules (:mod:`.pipeline`, :mod:`.package`) are imported
directly rather than re-exported here, so lower layers can import
:mod:`stubpy.core.context` without pulling in the emitters.
"""
from .context import AliasEntry, StubContext
from .diagnostics import Diagnostic, DiagnosticCollector, DiagnosticLevel, DiagnosticStage
from .results import PackageResult

__all__ = [
    "AliasEntry",
    "Diagnostic",
    "DiagnosticCollector",
    "DiagnosticLevel",
    "DiagnosticStage",
    "PackageResult",
    "StubContext",
]
