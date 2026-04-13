"""
stubpy.context
==============

Run-scoped mutable state for a single stub-generation pass.

Every call to :func:`~stubpy.generator.generate_stub` creates a fresh
:class:`StubContext`. Keeping state in a dataclass rather than
module-level globals makes the generator fully re-entrant and each
unit test independently isolated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple

from .diagnostics import DiagnosticCollector


class ExecutionMode(Enum):
    """Controls whether the target module is executed during stub generation.

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
    """Per-run configuration options for stub generation.

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
    union_style : str
        Output style for union annotations.  ``"modern"`` emits PEP 604
        ``X | Y`` syntax (e.g. ``str | None``); ``"legacy"`` emits
        ``Optional[X]`` / ``Union[X, Y]``.  Defaults to ``"modern"``.
    include_docstrings : bool
        When ``True``, copy the docstring from each function, method, and
        class into the generated stub as a literal string body instead of
        ``...``.  Useful when a stub doubles as quick-reference documentation
        without requiring the original source.  Defaults to ``False``.
    alias_style : str
        Output format for type alias declarations.

        - ``"compatible"`` (default) — always emit ``Name: TypeAlias = <rhs>``
          using the ``TypeAlias`` annotation from :mod:`typing`.  Works on all
          Python 3.10+ versions.
        - ``"pep695"`` — emit the Python 3.12+ ``type Name = <rhs>`` soft-keyword
          form (PEP 695).  Only use this when your project targets Python 3.12+.
        - ``"auto"`` — use ``pep695`` when running on Python 3.12+, otherwise
          fall back to ``compatible``.
    exclude : list of str
        Glob patterns (relative to the package root) for files to skip
        during package processing.  Only used by
        :func:`~stubpy.generator.generate_package`.  Defaults to ``[]``.
    output_dir : str or None
        Default output directory for package processing.  ``None`` means
        stubs are written alongside the source files.  Defaults to ``None``.
    infer_types_from_docstrings : bool
        When ``True``, attempt to infer parameter and return types from
        NumPy, Google, or Sphinx-style docstrings for functions and methods
        that lack explicit annotations.  Inferred types are emitted as
        inline ``# type:`` comments rather than live annotations, making
        their origin clearly visible.  Defaults to ``False``.
    incremental_update : bool
        When ``True``, wrap the generated stub in
        ``# stubpy: auto-generated begin/end`` markers and merge it into
        any existing ``.pyi`` file, preserving content outside the markers.
        When ``False`` (default) the ``.pyi`` is overwritten completely.
    """
    execution_mode:  ExecutionMode = ExecutionMode.RUNTIME
    include_private: bool          = False
    respect_all:     bool          = True
    verbose:         bool          = False
    strict:          bool          = False
    union_style:      str           = "modern"
    alias_style: str           = "compatible"
    include_docstrings: bool        = False
    exclude:          list[str]     = field(default_factory=list)
    output_dir:       str | None    = None
    infer_types_from_docstrings: bool = False
    incremental_update: bool = False


class AliasEntry(NamedTuple):
    """A pairing of a live annotation object with its stub alias string.

    Examples
    --------
    >>> entry = AliasEntry(annotation=str | float | int, alias_str="types.Length")
    >>> entry.alias_str
    'types.Length'
    """
    annotation: Any
    alias_str:  str


@dataclass
class StubContext:
    """Mutable state container scoped to one stub-generation run.

    Create one instance per :func:`~stubpy.generator.generate_stub` call,
    or pass a pre-configured instance to supply custom options.

    Attributes
    ----------
    alias_registry : list of AliasEntry
        Registered type aliases from imported sub-modules.
    type_module_imports : dict
        Import statements for alias sub-modules, keyed by local name.
    used_type_imports : dict
        Subset of *type_module_imports* actually referenced in the stub.
    config : StubConfig
        Per-run options (execution mode, privacy, verbosity, etc.).
    diagnostics : DiagnosticCollector
        Accumulated warnings and errors from the pipeline.
    symbol_table : SymbolTable or None
        Populated after the symbol-table stage; ``None`` until then.
    all_exports : set of str or None
        Contents of ``__all__`` from the target module, or ``None``.
    module_namespace : dict
        The full ``__dict__`` of the loaded module, populated after stage 1
        (module loading).  Used by :func:`~stubpy.resolver.resolve_function_params`
        to look up forwarding-target callables by name.  Empty in AST-only mode.

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

    alias_registry:      list[AliasEntry]  = field(default_factory=list)
    type_module_imports: dict[str, str]    = field(default_factory=dict)
    used_type_imports:   dict[str, str]    = field(default_factory=dict)

    config:           StubConfig           = field(default_factory=StubConfig)
    diagnostics:      DiagnosticCollector  = field(default_factory=DiagnosticCollector)
    symbol_table:     Any | None           = field(default=None)
    all_exports:      set[str] | None      = field(default=None)
    module_namespace: dict[str, Any]       = field(default_factory=dict)

    def lookup_alias(self, annotation: Any) -> str | None:
        """Return the alias string for *annotation* if registered, else ``None``.

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
