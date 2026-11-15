"""Run-scoped mutable state for one stub-generation pass."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from stubpy.config.options import StubConfig

from .diagnostics import DiagnosticCollector


class AliasEntry(NamedTuple):
    """A live annotation object paired with the alias string emitted for it.

    Examples
    --------
    >>> entry = AliasEntry(annotation=str | float | int, alias_str="types.Length")
    >>> entry.alias_str
    'types.Length'
    """
    annotation: Any
    alias_str: str


@dataclass
class StubContext:
    """Mutable state scoped to one :func:`~stubpy.generate_stub` run.

    Pass a pre-built instance to supply custom options or to inspect
    diagnostics afterwards.

    Attributes
    ----------
    alias_registry : list of AliasEntry
        Type aliases registered from imported sub-modules.
    type_module_imports : dict
        Import statements for alias sub-modules, keyed by local name.
    used_type_imports : dict
        Subset of *type_module_imports* actually referenced in the stub.
    config : StubConfig
        Per-run options.
    diagnostics : DiagnosticCollector
        Warnings and errors from the pipeline.
    symbol_table : SymbolTable or None
        Populated by the symbol-table stage.
    all_exports : set of str or None
        Contents of the target module's ``__all__``, if any.
    module_namespace : dict
        ``__dict__`` of the loaded module, used to look up forwarding
        targets.  Empty in AST-only mode.

    Examples
    --------
    >>> ctx = StubContext()
    >>> ctx.diagnostics.summary()
    '0 errors, 0 warnings, 0 infos'
    >>> ctx.config.execution_mode.value
    'runtime'
    """

    alias_registry: list[AliasEntry] = field(default_factory=list)
    type_module_imports: dict[str, str] = field(default_factory=dict)
    used_type_imports: dict[str, str] = field(default_factory=dict)

    config: StubConfig = field(default_factory=StubConfig)
    diagnostics: DiagnosticCollector = field(default_factory=DiagnosticCollector)
    symbol_table: Any | None = field(default=None)
    all_exports: set[str] | None = field(default=None)
    module_namespace: dict[str, Any] = field(default_factory=dict)

    def lookup_alias(self, annotation: Any) -> str | None:
        """Return the alias string registered for *annotation*, or ``None``.

        A hit also marks the alias module's import as used.

        Examples
        --------
        >>> ctx = StubContext()
        >>> ctx.alias_registry.append(AliasEntry(str | int, "types.T"))
        >>> ctx.type_module_imports["types"] = "from pkg import types"
        >>> ctx.lookup_alias(str | int)
        'types.T'
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
