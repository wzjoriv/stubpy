"""Import ``.py`` files as live modules for runtime introspection.

Files inside a package are imported by their dotted name with the package's
import root first on :data:`sys.path`, so relative imports work.  Loose
scripts are executed from their file under a synthetic module name.  A
:class:`ModuleLoader` imports each module once and, on :meth:`~ModuleLoader.close`,
restores :data:`sys.path` and drops the modules it imported.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any, NamedTuple

from stubpy._constants import SOURCE_ROOT_NAMES, TARGET_MODULE_PREFIX
from stubpy.core.diagnostics import DiagnosticCollector, DiagnosticStage


class ModuleLoadError(ImportError):
    """Raised when executing a target module fails; ``cause`` is the original exception."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class ModuleReplacedError(ModuleLoadError):
    """Raised when a module replaces its own ``sys.modules`` entry with a non-module object."""


class LoadedModule(NamedTuple):
    """A module loaded for stubbing: the live object, its source path and its ``__name__``."""
    module: types.ModuleType
    path: Path
    name: str


class ImportTarget(NamedTuple):
    """Where a file is importable from: the ``sys.path`` root and the dotted module name."""
    root: Path
    name: str


def _same_file(a: str | os.PathLike, b: str | os.PathLike) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _is_package_dir(folder: Path) -> bool:
    return (folder / "__init__.py").is_file()


def _is_namespace_dir(folder: Path, root: Path | None) -> bool:
    """Return ``True`` for a folder without ``__init__.py`` strictly beneath the explicit *root*."""
    if root is None or folder == root or root not in folder.parents:
        return False
    return folder.name.isidentifier() and folder.name not in SOURCE_ROOT_NAMES


def find_import_target(path: str | Path, root: str | Path | None = None) -> ImportTarget | None:
    """Return the import root and dotted name of *path*, or ``None`` for a loose script.

    Folders with an ``__init__.py`` are packages.  Beneath an explicit *root*,
    folders without one are treated as namespace packages, except ``src``-style
    source roots.

    Examples
    --------
    >>> find_import_target("/tmp/no_such_dir/script.py") is None
    True
    """
    file = Path(path).resolve()
    root_dir = Path(root).resolve() if root is not None else None
    parts = [] if file.name == "__init__.py" else [file.stem]
    folder = file.parent
    while _is_package_dir(folder) or _is_namespace_dir(folder, root_dir):
        parts.insert(0, folder.name)
        folder = folder.parent
    if len(parts) < 2 and file.name != "__init__.py":
        return None
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return ImportTarget(folder, ".".join(parts))


def _extension_or_builtin(module: Any) -> bool:
    """Return ``True`` for modules that cannot be safely re-imported once dropped."""
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) or getattr(module, "__file__", None) or ""
    if origin in ("built-in", "frozen"):
        return True
    return origin.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))


class ModuleLoader:
    """Import target files for one run; undo the import side effects on :meth:`close`.

    Parameters
    ----------
    root : str or Path, optional
        Explicit project or package root.  Folders without ``__init__.py``
        beneath it are imported as namespace packages.

    Examples
    --------
    >>> with ModuleLoader() as loader:  # doctest: +SKIP
    ...     loaded = loader.load("pkg/mod.py")
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self._loaded: dict[Path, LoadedModule] = {}
        self._failed: dict[str, BaseException] = {}
        self._modules_before: set[str] | None = None
        self._path_before: list[str] = []
        self._synthetic: set[str] = set()
        self._roots: set[str] = set()

    def __enter__(self) -> ModuleLoader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def load(self, filepath: str | Path, diagnostics: DiagnosticCollector | None = None) -> LoadedModule:
        """Import *filepath* once per loader and return it.

        Raises :exc:`FileNotFoundError` for a missing file and
        :exc:`ModuleLoadError` when the module cannot be imported; the
        original exception is kept as ``cause``.
        """
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        cached = self._loaded.get(path)
        if cached is not None:
            return cached
        if self._modules_before is None:
            self._modules_before = set(sys.modules)
            self._path_before = [os.path.normcase(os.path.realpath(p)) for p in sys.path if p]
            importlib.invalidate_caches()

        target = find_import_target(path, self.root)
        loaded: LoadedModule | None = None
        if target is not None:
            module = self._import_dotted(path, target)
            module_file = getattr(module, "__file__", None)
            if isinstance(module, types.ModuleType) and module_file and _same_file(module_file, path):
                loaded = LoadedModule(module, path, target.name)
            elif not isinstance(module, types.ModuleType):
                raise ModuleReplacedError(
                    f"{target.name} replaces itself in sys.modules with a "
                    f"{type(module).__name__} object, not a module",
                )
            elif diagnostics is not None:
                diagnostics.warning(
                    DiagnosticStage.LOAD, path.name,
                    f"Importing {target.name!r} gives {module_file or 'a module without a file'}, "
                    f"not {path}; loading the file directly instead",
                )
        if loaded is None:
            loaded = self._exec_file(path)
        self._loaded[path] = loaded
        return loaded

    def _import_dotted(self, path: Path, target: ImportTarget) -> Any:
        """Import *target* with its root first on ``sys.path``; return ``sys.modules[name]``."""
        parts = target.name.split(".")
        for i in range(1, len(parts) + 1):
            failed = self._failed.get(".".join(parts[:i]))
            if failed is not None:
                raise ModuleLoadError(
                    f"{'.'.join(parts[:i])} failed to import: {type(failed).__name__}: {failed}",
                    failed,
                )
        root = str(target.root)
        normalised = os.path.normcase(os.path.realpath(root))
        if normalised not in self._path_before:
            self._roots.add(normalised)
        with _ImportState(path, [root]):
            try:
                importlib.import_module(target.name)
            except (Exception, SystemExit) as exc:
                self._failed[target.name] = exc
                raise _load_error(exc) from exc
        return sys.modules.get(target.name)

    def _exec_file(self, path: Path) -> LoadedModule:
        """Execute a loose script under a unique synthetic module name."""
        module_name = f"{TARGET_MODULE_PREFIX}{path.stem}"
        n = 1
        while module_name in sys.modules or module_name in self._synthetic:
            n += 1
            module_name = f"{TARGET_MODULE_PREFIX}{path.stem}_{n}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ModuleLoadError(f"Cannot create module spec for: {path}")
        module = importlib.util.module_from_spec(spec)
        self._synthetic.add(module_name)
        self._roots.add(os.path.normcase(os.path.realpath(path.parent)))
        sys.modules[module_name] = module
        with _ImportState(path, [str(path.parent), str(path.parent.parent)]):
            try:
                spec.loader.exec_module(module)
            except (Exception, SystemExit) as exc:
                sys.modules.pop(module_name, None)
                raise _load_error(exc) from exc
        return LoadedModule(module, path, module_name)

    def _owns(self, name: str, module: Any) -> bool:
        """Return ``True`` when *module* was loaded from one of the stubbed roots (or replaced its entry)."""
        if name in self._synthetic or not isinstance(module, types.ModuleType):
            return True
        location = getattr(module, "__file__", None)
        if not location:
            paths = list(getattr(module, "__path__", None) or [])
            location = paths[0] if paths else None
        if not location:
            return False
        folder = os.path.normcase(os.path.realpath(location))
        for root in self._roots:
            if not folder.startswith(root + os.sep):
                continue
            deeper = [p for p in self._path_before if p.startswith(root + os.sep)]
            if not any(folder.startswith(p + os.sep) for p in deeper):
                return True
        return False

    def close(self) -> None:
        """Drop the modules this loader imported from roots it put on ``sys.path``, and loose scripts.

        Modules importable without the loader (the standard library,
        installed packages, roots already on ``sys.path``) stay loaded, as do
        packages containing extension modules, which cannot be safely re-imported.
        """
        if self._modules_before is None:
            return
        new = {name: sys.modules.get(name) for name in list(sys.modules) if name not in self._modules_before}
        keep_tops = {name.partition(".")[0] for name, mod in new.items() if _extension_or_builtin(mod)}
        for name, module in new.items():
            if name.partition(".")[0] not in keep_tops and self._owns(name, module):
                sys.modules.pop(name, None)
        self._loaded.clear()
        self._failed.clear()
        self._roots.clear()
        self._synthetic.clear()
        self._modules_before = None


class _ImportState:
    """Context manager that sets ``sys.path``, ``sys.argv`` and bytecode writing for one import."""

    def __init__(self, path: Path, roots: list[str]) -> None:
        self._path = path
        self._roots = roots

    def __enter__(self) -> None:
        self._saved_path = list(sys.path)
        self._saved_argv = list(sys.argv)
        self._saved_bytecode = sys.dont_write_bytecode
        sys.path[:0] = [r for r in self._roots if r not in sys.path[: len(self._roots)]]
        sys.argv = [str(self._path)]
        sys.dont_write_bytecode = True

    def __exit__(self, *exc: object) -> None:
        sys.path[:] = self._saved_path
        sys.argv = self._saved_argv
        sys.dont_write_bytecode = self._saved_bytecode


def _load_error(exc: BaseException) -> BaseException:
    """Return the exception to raise for a failed import: ``SystemExit`` becomes :exc:`ModuleLoadError`."""
    if isinstance(exc, SystemExit):
        return ModuleLoadError(f"SystemExit: {exc.code}", exc)
    return exc


def describe_load_error(exc: BaseException) -> str:
    """Return ``"Type: message"`` for *exc*; :exc:`ModuleLoadError` messages already have that form."""
    if isinstance(exc, ModuleLoadError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


def load_module(
    filepath: str,
    diagnostics: DiagnosticCollector | None = None,
) -> tuple[types.ModuleType, Path, str]:
    """Load *filepath* on its own and return ``(module, resolved_path, module_name)``.

    The module stays in :data:`sys.modules`.  Load errors are recorded in
    *diagnostics*, when given, and re-raised.  Raises
    :exc:`FileNotFoundError` for a missing file.
    """
    loader = ModuleLoader()
    try:
        loaded = loader.load(filepath, diagnostics)
    except FileNotFoundError as exc:
        if diagnostics is not None:
            diagnostics.error(DiagnosticStage.LOAD, str(Path(filepath).resolve()), str(exc))
        raise
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.error(
                DiagnosticStage.LOAD, str(filepath),
                f"Module execution failed: {describe_load_error(exc)}",
            )
        raise
    return loaded.module, loaded.path, loaded.name
