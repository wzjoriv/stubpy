"""Import a ``.py`` file as a live module for runtime introspection."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from stubpy._constants import TARGET_MODULE_PREFIX
from stubpy.core.diagnostics import DiagnosticCollector, DiagnosticStage


def load_module(
    filepath: str,
    diagnostics: DiagnosticCollector | None = None,
) -> tuple[types.ModuleType, Path, str]:
    """Load *filepath* as a module named ``_stubpy_target_<stem>``.

    The file's parent and grandparent directories are on :data:`sys.path`
    only while the module executes.  Load errors are recorded in
    *diagnostics*, when given, and re-raised.

    Returns ``(module, resolved_path, module_name)``.  Raises
    :exc:`FileNotFoundError` for a missing file and :exc:`ImportError` when
    no module spec can be created.
    """
    path = Path(filepath).resolve()
    if not path.exists():
        msg = f"No such file: {path}"
        if diagnostics is not None:
            diagnostics.error(DiagnosticStage.LOAD, str(path), msg)
        raise FileNotFoundError(msg)

    search_paths = [str(path.parent), str(path.parent.parent)]
    inserted: list[str] = []
    for p in search_paths:
        if p not in sys.path:
            sys.path.insert(0, p)
            inserted.append(p)

    try:
        module_name = f"{TARGET_MODULE_PREFIX}{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            msg = f"Cannot create module spec for: {path}"
            if diagnostics is not None:
                diagnostics.error(DiagnosticStage.LOAD, str(path), msg)
            raise ImportError(msg)

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except (FileNotFoundError, ImportError):
        raise
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.error(
                DiagnosticStage.LOAD, str(path),
                f"Module execution failed: {type(exc).__name__}: {exc}"
            )
        raise
    finally:
        for p in inserted:
            try:
                sys.path.remove(p)
            except ValueError:
                pass

    return module, path, module_name
