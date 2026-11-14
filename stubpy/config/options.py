"""Run options: :class:`StubConfig` and :class:`ExecutionMode`."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExecutionMode(Enum):
    """Controls whether the target module is executed during stub generation.

    Attributes
    ----------
    RUNTIME
        Execute the module and use live objects for full introspection,
        including ``**kwargs`` MRO back-tracing.  The default.
    AST_ONLY
        Parse the AST only; no module execution.  Safer but less precise.
    AUTO
        Execute the module when possible; fall back to AST-only on load failures.
    """
    RUNTIME = "runtime"
    AST_ONLY = "ast_only"
    AUTO = "auto"


EXECUTION_MODES: dict[str, ExecutionMode] = {
    "runtime": ExecutionMode.RUNTIME,
    "ast_only": ExecutionMode.AST_ONLY,
    "auto": ExecutionMode.AUTO,
}


@dataclass
class StubConfig:
    """Per-run configuration options for stub generation.

    Parameters
    ----------
    execution_mode : ExecutionMode
        Whether to execute the module.  Defaults to ``RUNTIME``.
    include_private : bool
        Include symbols whose names start with ``_``.  Defaults to ``False``.
    respect_all : bool
        When ``__all__`` is present, stub only the names it lists.  Defaults to ``True``.
    verbose : bool
        Print INFO-level diagnostics.  Defaults to ``False``.
    strict : bool
        Any ERROR diagnostic causes a non-zero exit.  Defaults to ``False``.
    union_style : str
        ``"modern"`` emits PEP 604 ``X | None``; ``"legacy"`` emits
        ``Optional[X]`` / ``Union[X, Y]``.  Defaults to ``"modern"``.
    alias_style : str
        ``"compatible"`` emits ``Name: TypeAlias = rhs``; ``"pep695"`` emits
        ``type Name = rhs``; ``"auto"`` picks ``pep695`` on Python 3.12+.
        Defaults to ``"compatible"``.
    include_docstrings : bool
        Embed each symbol's docstring as its stub body instead of ``...``.
        Defaults to ``False``.
    exclude : list of str
        Glob patterns, relative to the package root, of files skipped by
        :func:`~stubpy.generate_package`.  Defaults to ``[]``.
    output_dir : str or None
        Default output directory for package processing; ``None`` writes
        stubs alongside the sources.
    infer_types_from_docstrings : bool
        Infer missing parameter types from NumPy, Google or Sphinx docstrings,
        emitted as ``# type:`` comments.  Defaults to ``False``.
    incremental_update : bool
        Wrap the stub in ``# stubpy: auto-generated begin/end`` markers and
        merge it into an existing ``.pyi``.  Defaults to ``False``.
    resolve_kwargs : bool
        Expand ``**kwargs`` into the concrete parameters it forwards to.
        Defaults to ``True``.
    resolve_args : bool
        Expand ``*args`` into the concrete positional parameters it forwards to.
        Defaults to ``True``.
    """
    execution_mode: ExecutionMode = ExecutionMode.RUNTIME
    include_private: bool = False
    respect_all: bool = True
    verbose: bool = False
    strict: bool = False
    union_style: str = "modern"
    alias_style: str = "compatible"
    include_docstrings: bool = False
    exclude: list[str] = field(default_factory=list)
    output_dir: str | None = None
    infer_types_from_docstrings: bool = False
    incremental_update: bool = False
    resolve_kwargs: bool = True
    resolve_args: bool = True
