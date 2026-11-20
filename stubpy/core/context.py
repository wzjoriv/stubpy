"""
Run-scoped mutable state for one stub-generation pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

from stubpy.config.options import Config

from .diagnostics import DiagnosticCollector


class AliasEntry(NamedTuple):
    """A live annotation object paired with the alias string emitted for it.

    Parameters
    ----------
    annotation : object
        The annotation object as seen at runtime.
    alias_str : str
        The text written in the stub, e.g. ``"types.Length"``.

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
    """Mutable state for stubbing one module.

    Every emitter and annotation handler receives it; extensions read
    ``ctx.config`` and record issues in ``ctx.diagnostics``.  Every field is
    optional and starts empty, so ``StubContext()`` is valid.

    Parameters
    ----------
    alias_registry : list of AliasEntry
        Type aliases registered from imported sub-modules.
    type_module_imports : dict
        Import statements for alias sub-modules, keyed by local name.
    used_type_imports : dict
        Subset of *type_module_imports* actually referenced in the stub.
    config : Config
        Per-run options.
    diagnostics : DiagnosticCollector
        Warnings and errors from the pipeline.
    symbol_table : SymbolTable or None
        Populated by the symbol-table stage.
    all_exports : set of str or None
        Contents of the target module's ``__all__``, if any.
    all_order : list of str
        The same names in their ``__all__`` order, for the stub's own ``__all__``.
    star_exports : dict
        For each ``from m import *`` of the module, the names it binds when
        ``m`` declares ``__all__``; the stub re-exports them one by one.
    module_namespace : dict
        ``__dict__`` of the loaded module, used to look up forwarding
        targets.  Empty when the module was not imported.
    module_name : str
        ``__name__`` of the target module (synthetic for loose scripts).
    import_map : dict
        ``{local_name: import_statement}`` for the imports in the source.
    extra_imports : dict
        Imports the emitters needed beyond the source's annotations, keyed
        by local name (for example the class of an enum default).
    module_loader : ModuleLoader or None
        Loader shared by a package run; ``None`` makes each run use its own.
    branch_imports : list of ImportInfo
        Imports inside version branches; the body writes the ones it needs
        inside their branch instead of the header.
    source_index : SourceIndex or None
        Harvested sources shared by a run, for back-tracing without imports.
    source_module : SourceModule or None
        The module being stubbed in that index; variadics are resolved from
        it when the module was not imported (``module_namespace`` is empty).
    requested_names : set of str
        Names other modules of the run import from this one; they are kept in
        the stub even when private or outside ``__all__``.
    submodule : str
        For a compiled extension, the dotted path of the attribute submodule to stub
        (``"fft"`` for ``pkg.fft``); ``""`` for the extension itself.
    submodules : list of str
        The attribute submodules of the compiled module just stubbed, by attribute name.

    Examples
    --------
    >>> ctx = StubContext()
    >>> ctx.diagnostics.summary()
    '0 errors, 0 warnings, 0 infos'
    >>> ctx.config.may_import
    True
    """

    alias_registry: list[AliasEntry] = field(default_factory=list)
    type_module_imports: dict[str, str] = field(default_factory=dict)
    used_type_imports: dict[str, str] = field(default_factory=dict)

    config: Config = field(default_factory=Config)
    diagnostics: DiagnosticCollector = field(default_factory=DiagnosticCollector)
    symbol_table: Any | None = field(default=None)
    all_exports: set[str] | None = field(default=None)
    all_order: list[str] = field(default_factory=list)
    star_exports: dict[str, list[str]] = field(default_factory=dict)
    module_namespace: dict[str, Any] = field(default_factory=dict)
    module_name: str = ""
    import_map: dict[str, str] = field(default_factory=dict)
    extra_imports: dict[str, str] = field(default_factory=dict)
    module_loader: Any | None = field(default=None)
    branch_imports: list[Any] = field(default_factory=list)
    source_index: Any | None = field(default=None)
    source_module: Any | None = field(default=None)
    requested_names: set[str] = field(default_factory=set)
    submodule: str = ""
    submodules: list[str] = field(default_factory=list)
    _alias_index: dict[Any, str] | None = field(default=None, repr=False, compare=False)
    _alias_index_size: int = field(default=-1, repr=False, compare=False)

    def lookup_alias(self, annotation: Any) -> str | None:
        """Return the alias string registered for *annotation*, or ``None``.

        A hit also marks the alias module's import as used.

        Parameters
        ----------
        annotation : object
            The annotation to look up; unhashable ones are compared by equality.

        Returns
        -------
        str or None
            The registered alias text, or ``None`` when there is none.

        Examples
        --------
        >>> ctx = StubContext()
        >>> ctx.alias_registry.append(AliasEntry(str | int, "types.T"))
        >>> ctx.type_module_imports["types"] = "from pkg import types"
        >>> ctx.lookup_alias(str | int)
        'types.T'
        """
        if not self.alias_registry:
            return None
        alias_str = self._indexed_alias(annotation)
        if alias_str is None:
            return None
        module_alias = alias_str.split(".")[0]
        if module_alias in self.type_module_imports:
            self.used_type_imports[module_alias] = self.type_module_imports[module_alias]
        return alias_str

    def _indexed_alias(self, annotation: Any) -> str | None:
        """Look *annotation* up in a hash index of the registry, scanning linearly when unhashable."""
        if self._alias_index is None or self._alias_index_size != len(self.alias_registry):
            index: dict[Any, str] = {}
            for entry in self.alias_registry:
                try:
                    index.setdefault(entry.annotation, entry.alias_str)
                except Exception:
                    pass
            self._alias_index = index
            self._alias_index_size = len(self.alias_registry)
        try:
            return self._alias_index.get(annotation)
        except TypeError:
            pass
        for entry in self.alias_registry:
            try:
                if entry.annotation == annotation:
                    return entry.alias_str
            except Exception:
                pass
        return None
