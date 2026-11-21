"""
The :class:`ModuleLoader`: imports each module once and restores ``sys.path`` and ``sys.modules`` on close.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import re
import sys
import types
from pathlib import Path
from typing import Any, NamedTuple

from stubpy._constants import TARGET_MODULE_PREFIX
from stubpy.compiled.detect import is_current_abi, is_extension_file, module_stem
from stubpy.state.diagnostics import DiagnosticCollector, Stage

from . import vfs
from ._extension import extension_alone
from ._guard import ImportBlockedError, import_guard
from ._importing import ImportState, ImportTarget, find_import_target, same_file
from ._load_errors import ModuleLoadError, ModuleReplacedError, _load_error


class LoadedModule(NamedTuple):
    """A module loaded for stubbing: the live object, its source path and its ``__name__``.

    Attributes
    ----------
    module : types.ModuleType
        The imported module.
    path : Path
        Resolved path of its source file.
    name : str
        The name it is registered under in ``sys.modules``.

    Examples
    --------
    >>> import types
    >>> loaded = LoadedModule(types.ModuleType("mod"), Path("mod.py"), "mod")
    >>> loaded.name
    'mod'
    """
    module: types.ModuleType
    path: Path
    name: str


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
        beneath it are imported as namespace packages. Defaults to None.
    policy : ImportPolicy, optional
        Which modules may be imported; a blocked import, direct or indirect,
        raises :exc:`ImportBlockedError`.  ``None`` allows everything. Defaults to None.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = Path(d, "script.py").write_text("X = 1\\n")
    ...     with ModuleLoader() as loader:
    ...         loader.load(Path(d, "script.py")).module.X
    1
    """

    def __init__(self, root: str | Path | None = None, policy: Any = None) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.policy = policy
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

        A file already loaded by this loader is returned from the cache.

        Parameters
        ----------
        filepath : str or Path
            The ``.py`` file or compiled extension to import.
        diagnostics : DiagnosticCollector, optional
            Collector the caller reports failures to. Defaults to None.

        Returns
        -------
        LoadedModule
            The live module, its resolved path and its name.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        ModuleLoadError
            If the module cannot be imported; the original exception is kept as ``cause``.
        ModuleReplacedError
            If the module replaces its own ``sys.modules`` entry with a non-module object.
        ImportBlockedError
            If the import policy refuses a module the file imports.

        Examples
        --------
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as d:
        ...     _ = Path(d, "script.py").write_text("X = 1\\n")
        ...     with ModuleLoader() as loader:
        ...         loaded = loader.load(Path(d, "script.py"))
        ...         loaded is loader.load(Path(d, "script.py"))
        True
        """
        path = Path(filepath).resolve()
        if not vfs.is_file(path):
            raise FileNotFoundError(f"No such file: {path}")
        cached = self._loaded.get(path)
        if cached is not None:
            return cached
        extension = is_extension_file(path)
        if extension and not is_current_abi(path):
            raise ModuleLoadError(
                f"{path.name} was built for another interpreter; this one imports "
                f"{', '.join(importlib.machinery.EXTENSION_SUFFIXES)}",
            )
        if self._modules_before is None:
            self._modules_before = set(sys.modules)
            self._path_before = [os.path.normcase(os.path.realpath(p)) for p in sys.path if p]
            importlib.invalidate_caches()

        target = find_import_target(path, self.root)
        name = target.name if target is not None else module_stem(path)
        if self.policy is not None and not self.policy.allows(name):
            raise ImportBlockedError(name)
        with import_guard(self.policy) as guard:
            try:
                loaded = self._load(path, target, extension, diagnostics)
            except ImportBlockedError:
                raise
            except Exception as exc:
                if guard is not None and guard.blocked:
                    raise ImportBlockedError(guard.blocked[0]) from exc
                raise
        self._loaded[path] = loaded
        return loaded

    def _load(self, path: Path, target: ImportTarget | None, extension: bool,
              diagnostics: DiagnosticCollector | None) -> LoadedModule:
        loaded: LoadedModule | None = None
        if target is not None and extension and "." in target.name:
            try:
                module = self._import_dotted(path, target)
            except ModuleLoadError as exc:
                module = extension_alone(path, target, exc)
                if diagnostics is not None:
                    diagnostics.warning(Stage.LOAD, path.name, f"{exc}; loaded {target.name} on its own instead")
        elif target is not None:
            module = self._import_dotted(path, target)
        if target is not None:
            module_file = getattr(module, "__file__", None)
            if isinstance(module, types.ModuleType) and module_file and same_file(module_file, path):
                loaded = LoadedModule(module, path, target.name)
            elif extension:
                raise ModuleLoadError(
                    f"Importing {target.name!r} gives {module_file or 'a module without a file'}, not {path}",
                )
            elif not isinstance(module, types.ModuleType):
                raise ModuleReplacedError(
                    f"{target.name} replaces itself in sys.modules with a "
                    f"{type(module).__name__} object, not a module",
                )
            elif diagnostics is not None:
                diagnostics.warning(
                    Stage.LOAD, path.name,
                    f"Importing {target.name!r} gives {module_file or 'a module without a file'}, "
                    f"not {path}; loading the file directly instead",
                )
        if loaded is None:
            loaded = self._exec_file(path)
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
        with ImportState(path, [root]):
            try:
                importlib.import_module(target.name)
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                self._failed[target.name] = exc
                raise _load_error(exc) from exc
        return sys.modules.get(target.name)

    def _exec_file(self, path: Path) -> LoadedModule:
        """Execute a loose script under a unique synthetic module name."""
        if is_extension_file(path):
            return self._exec_extension(path)
        module_name = f"{TARGET_MODULE_PREFIX}{_safe(path.stem)}"
        n = 1
        while module_name in sys.modules or module_name in self._synthetic:
            n += 1
            module_name = f"{TARGET_MODULE_PREFIX}{_safe(path.stem)}_{n}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ModuleLoadError(f"Cannot create module spec for: {path}")
        module = importlib.util.module_from_spec(spec)
        self._synthetic.add(module_name)
        self._roots.add(os.path.normcase(os.path.realpath(path.parent)))
        sys.modules[module_name] = module
        with ImportState(path, [str(path.parent), str(path.parent.parent)]):
            try:
                spec.loader.exec_module(module)
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                sys.modules.pop(module_name, None)
                raise _load_error(exc) from exc
        return LoadedModule(module, path, module_name)

    def _exec_extension(self, path: Path) -> LoadedModule:
        """Load a loose extension module under its own name (its init function is named after it)."""
        name = module_stem(path)
        existing = sys.modules.get(name)
        if existing is not None and same_file(getattr(existing, "__file__", "") or "", path):
            return LoadedModule(existing, path, name)
        if existing is not None:
            raise ModuleLoadError(f"A different module named {name!r} is already imported")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ModuleLoadError(f"Cannot create module spec for: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            sys.modules.pop(name, None)
            raise _load_error(exc) from exc
        return LoadedModule(module, path, name)

    def _owns(self, name: str, module: Any) -> bool:
        """Return ``True`` when *module* was loaded from one of the stubbed roots (or replaced its entry)."""
        if name in self._synthetic or not isinstance(module, types.ModuleType):
            return True
        location = getattr(module, "__file__", None)
        if not location:
            try:
                paths = list(getattr(module, "__path__", None) or [])
            except Exception:
                return True
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

        Examples
        --------
        >>> loader = ModuleLoader()
        >>> loader.close()
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


def _safe(stem: str) -> str:
    """*stem* with every character that cannot appear in a module name replaced by ``_``."""
    return re.sub(r"\W", "_", stem)
