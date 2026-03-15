"""
stubpy.loader
=============

Dynamic module loading for stub generation.

Provides :func:`load_module`, which imports a ``.py`` file as a live
Python module so that :mod:`inspect` and :func:`typing.get_type_hints`
can introspect its classes and annotations at runtime.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def load_module(filepath: str) -> tuple[types.ModuleType, Path, str]:
    """Dynamically load a Python source file as an importable module.

    Temporarily extends :data:`sys.path` with the file's parent directory
    and its grandparent so that package-relative imports inside the target
    resolve correctly. Both paths are always removed in a ``finally``
    block regardless of errors.

    Parameters
    ----------
    filepath : str
        Path to the ``.py`` source file. Relative paths are resolved
        against the current working directory.

    Returns
    -------
    module : types.ModuleType
        The fully initialised module object.
    resolved_path : pathlib.Path
        Absolute path of the source file.
    module_name : str
        Synthetic name used to register the module in :data:`sys.modules`,
        of the form ``_stubpy_target_<stem>``.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist on disk.
    ImportError
        If :func:`importlib.util.spec_from_file_location` cannot create
        a module spec for the file.

    Examples
    --------
    >>> module, path, name = load_module("mypackage/shapes.py")  # doctest: +SKIP
    >>> path.suffix
    '.py'
    >>> name.startswith("_stubpy_target_")
    True
    """
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    search_paths = [str(path.parent), str(path.parent.parent)]
    inserted: list[str] = []
    for p in search_paths:
        if p not in sys.path:
            sys.path.insert(0, p)
            inserted.append(p)

    try:
        module_name = f"_stubpy_target_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for: {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        for p in inserted:
            try:
                sys.path.remove(p)
            except ValueError:
                pass

    return module, path, module_name
