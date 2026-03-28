"""
stubpy.context
==============

Run-scoped mutable state for a single stub-generation pass.

Every call to :func:`~stubpy.generator.generate_stub` creates a fresh
:class:`StubContext`. Keeping state in a dataclass rather than
module-level globals makes the generator fully re-entrant and each
unit test independently isolated.

New additions
-------------
:attr:`StubContext.diagnostics`
    A :class:`~stubpy.diagnostics.DiagnosticCollector` that replaces bare
    ``try/except pass`` blocks throughout the pipeline.

:attr:`StubContext.symbol_table`
    The :class:`~stubpy.symbols.SymbolTable` populated by the new AST
    pre-pass and runtime-introspection stages.

:attr:`StubContext.config`
    A :class:`StubConfig` dataclass holding per-run configuration options.

:attr:`StubContext.all_exports`
    The ``__all__`` names from the target module, or ``None`` when absent.

All new fields have defaults so that existing code using
``StubContext()`` continues to work without modification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple

from .diagnostics import DiagnosticCollector


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ExecutionMode(Enum):
    """
    Controls whether the target module is executed during stub generation.

    Attributes
    ----------
    RUNTIME
        Execute the module and use live objects for full introspection.
        This is the default and enables ``**kwargs`` MRO back-tracing.
    AST_ONLY
        Parse the AST only; no module execution.  Safer but less precise.
    AUTO
        Execute the module when possible; fall back to AST-only on load
        failures.
    """
    RUNTIME  = "runtime"
    AST_ONLY = "ast_only"
    AUTO     = "auto"


@dataclass
class StubConfig:
    """
    Per-run configuration options for stub generation.

    All fields have sensible defaults so callers need not supply any
    arguments for standard usage.

    Parameters
    ----------
    execution_mode : ExecutionMode
        Defaults to ``RUNTIME``.
    include_private : bool
        When ``True``, symbols whose names start with ``_`` are included.
        Defaults to ``False``.
    respect_all : bool
        When ``True`` and ``__all__`` is present, only names in ``__all__``
        are stubbed.  Defaults to ``True``.
    verbose : bool
        When ``True``, INFO-level diagnostics are printed.  Defaults to
        ``False``.
    strict : bool
        When ``True``, any ERROR diagnostic causes a non-zero exit.
        Defaults to ``False``.
    """
    execution_mode:  ExecutionMode = ExecutionMode.RUNTIME
    include_private: bool          = False
    respect_all:     bool          = True
    verbose:         bool          = False
    strict:          bool          = False


# ---------------------------------------------------------------------------
# Alias entry (unchanged from v0.1)
# ---------------------------------------------------------------------------

class AliasEntry(NamedTuple):
    """
    A pairing of a live annotation object with its stub alias string.

    Examples
    --------
    >>> entry = AliasEntry(annotation=str | float | int, alias_str="types.Length")
    >>> entry.alias_str
    'types.Length'
    """
    annotation: Any
    alias_str:  str


# ---------------------------------------------------------------------------
# Main context
# ---------------------------------------------------------------------------

@dataclass
class StubContext:
    """
    Mutable state container scoped to one stub-generation run.

    Create one instance per :func:`~stubpy.generator.generate_stub` call.

    v0.1 fields (unchanged)
    -----------------------
    alias_registry, type_module_imports, used_type_imports

    New additions
    -------------
    config, diagnostics, symbol_table, all_exports

    Examples
    --------
    >>> ctx = StubContext()
    >>> ctx.diagnostics.summary()
    '0 errors, 0 warnings, 0 infos'
    >>> ctx.config.execution_mode.value
    'runtime'
    >>> ctx.symbol_table is None
    True
    """

    # ── v0.1 fields ──────────────────────────────────────────────────────
    alias_registry:      list[AliasEntry]  = field(default_factory=list)
    type_module_imports: dict[str, str]    = field(default_factory=dict)
    used_type_imports:   dict[str, str]    = field(default_factory=dict)

    # ── New fields ────────────────────────────────────────────────────────────
    config:       StubConfig           = field(default_factory=StubConfig)
    diagnostics:  DiagnosticCollector  = field(default_factory=DiagnosticCollector)
    symbol_table: Any | None           = field(default=None)   # SymbolTable | None
    all_exports:  set[str] | None      = field(default=None)

    # ------------------------------------------------------------------
    # Alias lookup (unchanged from v0.1)
    # ------------------------------------------------------------------

    def lookup_alias(self, annotation: Any) -> str | None:
        """
        Return the alias string for *annotation* if registered, else ``None``.

        Examples
        --------
        >>> ctx = StubContext()
        >>> ctx.alias_registry.append(AliasEntry(str | int, "types.T"))
        >>> ctx.type_module_imports["types"] = "from pkg import types"
        >>> ctx.lookup_alias(str | int)
        'types.T'
        >>> ctx.lookup_alias(str | float) is None
        True
        """
        for entry in self.alias_registry:
            try:
                if entry.annotation == annotation:
                    module_alias = entry.alias_str.split(".")[0]
                    if module_alias in self.type_module_imports:
                        self.used_type_imports[module_alias] = (
                            self.type_module_imports[module_alias]
                        )
                    return entry.alias_str
            except Exception:
                pass
        return None
