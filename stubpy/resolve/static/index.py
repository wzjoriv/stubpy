"""
Package-wide index of harvested sources for one run, keyed by file and by dotted module name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stubpy.analysis import vfs
from stubpy.analysis.exports import harvest_file, module_file
from stubpy.analysis.harvest import ASTSymbols


def dotted_name(path: Path) -> str:
    """Return the import name of the source file *path*, walking up ``__init__.py`` folders."""
    parts = [] if path.name == "__init__.py" else [path.stem]
    folder = path.parent
    while vfs.is_file(folder / "__init__.py"):
        parts.insert(0, folder.name)
        folder = folder.parent
    return ".".join(parts) or path.stem


@dataclass(eq=False)
class SourceModule:
    """One harvested module: its file, dotted name and AST symbols."""
    path: Path
    name: str
    symbols: ASTSymbols

    @property
    def is_package(self) -> bool:
        """True for a package ``__init__.py``."""
        return self.path.name == "__init__.py"

    @property
    def package(self) -> str:
        """The package relative imports resolve against."""
        return self.name if self.is_package else self.name.rpartition(".")[0]


@dataclass
class SourceIndex:
    """Harvested modules shared by every stub of one run; nothing is imported.

    *resolver* caches the run's :class:`StaticResolver`.
    """
    _by_path: dict[Path, SourceModule | None] = field(default_factory=dict)
    resolver: Any = None
    _resolved: dict[Path, Path] = field(default_factory=dict, init=False, repr=False)
    _files: dict[tuple[Path, str], Path | None] = field(default_factory=dict, init=False, repr=False)

    def _resolve(self, path: Path) -> Path:
        """Return *path* resolved, memoised for the run."""
        path = Path(path)
        found = self._resolved.get(path)
        if found is None:
            found = self._resolved[path] = path.resolve()
        return found

    def harvested(self, path: Path) -> ASTSymbols | None:
        """Return the symbols already harvested for *path*, without harvesting it."""
        module = self._by_path.get(self._resolve(path))
        return module.symbols if module is not None else None

    def module_at(self, path: Path, symbols: ASTSymbols | None = None) -> SourceModule | None:
        """Return the :class:`SourceModule` of the file at *path*, harvesting it on first use."""
        path = self._resolve(path)
        if path not in self._by_path:
            symbols = symbols if symbols is not None else harvest_file(path)
            self._by_path[path] = SourceModule(path, dotted_name(path), symbols) if symbols is not None else None
        return self._by_path[path]

    def import_from(self, current: SourceModule, module: str) -> SourceModule | None:
        """Return the module *module* (leading dots allowed) names when imported from *current*."""
        key = (current.path.parent, module)
        if key not in self._files:
            self._files[key] = module_file(current.path, module)
        file = self._files[key]
        return self.module_at(file) if file is not None else None
