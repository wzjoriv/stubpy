"""
Import ``.py`` files as live modules for runtime introspection.
A :class:`ModuleLoader` imports each module once and restores ``sys.path`` on close.
"""
from __future__ import annotations

import types
from pathlib import Path

from stubpy.state.diagnostics import DiagnosticCollector, Stage

from ._guard import ImportBlockedError as ImportBlockedError
from ._importing import ImportTarget, find_import_target
from ._load_errors import ModuleLoadError, ModuleReplacedError, describe_load_error
from ._module_loader import LoadedModule, ModuleLoader

__all__ = [
    "ImportTarget",
    "LoadedModule",
    "ModuleLoadError",
    "ModuleLoader",
    "ModuleReplacedError",
    "describe_load_error",
    "find_import_target",
    "load_module",
]


def load_module(
    filepath: str,
    diagnostics: DiagnosticCollector | None = None,
) -> tuple[types.ModuleType, Path, str]:
    """Load *filepath* on its own and return ``(module, resolved_path, module_name)``.

    The module stays in :data:`sys.modules`.  Load errors are recorded in
    *diagnostics*, when given, and re-raised.

    Parameters
    ----------
    filepath : str
        The ``.py`` file to import.
    diagnostics : DiagnosticCollector, optional
        Receives an error entry when loading fails. Defaults to None.

    Returns
    -------
    tuple of (types.ModuleType, Path, str)
        The live module, its resolved path and its ``__name__``.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ModuleLoadError
        If executing the module fails.

    See Also
    --------
    ModuleLoader : Load several files and undo the import side effects.

    Examples
    --------
    >>> load_module("no_such_file.py")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    FileNotFoundError: No such file: ...no_such_file.py
    """
    loader = ModuleLoader()
    try:
        loaded = loader.load(filepath, diagnostics)
    except FileNotFoundError as exc:
        if diagnostics is not None:
            diagnostics.error(Stage.LOAD, str(Path(filepath).resolve()), str(exc))
        raise
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.error(
                Stage.LOAD, str(filepath),
                f"Module execution failed: {describe_load_error(exc)}",
            )
        raise
    return loaded.module, loaded.path, loaded.name
