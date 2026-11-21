"""
Run cache: a module whose source and package imports are unchanged since the last run reuses its stub.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from stubpy.config.options import Config
from stubpy.state.diagnostics import Diagnostic, Level, Stage

from .results import StubResult

CACHE_FILE = "stubs.json"


class RunCache:
    """Stub texts and diagnostics keyed by each module's source, its package imports and the run settings.

    Parameters
    ----------
    folder : pathlib.Path
        Where the cache file lives; created on :meth:`save`.
    config : Config
        The run options; a different config, stubpy or Python version starts from an empty cache.
    """

    def __init__(self, folder: Path, config: Config) -> None:
        from stubpy import __version__

        self.path = folder / CACHE_FILE
        self.salt = f"{__version__}|{sys.version}|{config!r}"
        self.entries: dict[str, dict[str, object]] = {}
        self.hits = 0
        self._digests: dict[Path, str] = {}
        self._imports: dict[Path, set[str]] = {}
        with contextlib.suppress(OSError, ValueError):
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("salt") == self.salt and isinstance(data.get("stubs"), dict):
                self.entries = data["stubs"]

    def key(self, source: Path, modules: dict[str, Path]) -> str:
        """The digest of *source* and every module of *modules* it imports, directly or not."""
        names = {name for name, path in modules.items() if path == source}
        seen: set[Path] = {source}
        queue = [source]
        while queue:
            path = queue.pop()
            package = next((n for n, p in modules.items() if p == path), "")
            for name in self._local_imports(path, package, modules):
                dep = modules[name]
                if dep not in seen:
                    seen.add(dep)
                    queue.append(dep)
        h = hashlib.sha256(self.salt.encode())
        for path in sorted(seen):
            h.update(str(path).encode() + b"\0" + self._digest(path).encode())
        h.update(",".join(sorted(names)).encode())
        return h.hexdigest()

    def get(self, source: Path, key: str, output: Path | None) -> StubResult | None:
        """The cached result of *source* under *key*, or ``None``."""
        entry = self.entries.get(str(source))
        if not entry or entry.get("key") != key:
            return None
        self.hits += 1
        notes = tuple(Diagnostic(Level(d[0]), Stage(d[1]), d[2], d[3]) for d in entry["diagnostics"])  # type: ignore[union-attr]
        return StubResult(str(entry["text"]), notes, source, str(entry["module"]), output)

    def put(self, key: str, result: StubResult) -> None:
        """Remember *result* (an unmerged render) under *key*."""
        if result.source is None or not result.ok:
            return
        self.entries[str(result.source)] = {
            "key": key, "text": result.text, "module": result.module_name,
            "diagnostics": [[int(d.level), d.stage.value, d.symbol, d.message] for d in result.diagnostics],
        }

    def save(self) -> None:
        """Write the cache file atomically; a folder that cannot be written is left alone."""
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"salt": self.salt, "stubs": self.entries}, f)
            os.replace(tmp, self.path)

    def _digest(self, path: Path) -> str:
        if path not in self._digests:
            try:
                self._digests[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                self._digests[path] = ""
        return self._digests[path]

    def _local_imports(self, path: Path, module: str, modules: dict[str, Path]) -> set[str]:
        """The names in *modules* that the source at *path* (module *module*) imports."""
        if path not in self._imports:
            self._imports[path] = _imports(path, module, path.name == "__init__.py")
        found = set()
        for name in self._imports[path]:
            while name and name not in modules:
                name = name.rpartition(".")[0]
            if name:
                found.add(name)
        return found


def _imports(path: Path, module: str, is_package: bool) -> set[str]:
    """Every dotted name *path* imports, relative imports resolved, ``from m import x`` giving ``m`` and ``m.x``.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "core.py"
    ...     _ = src.write_text("from . import util\\nimport os\\n")
    ...     sorted(_imports(src, "pkg.core", False))
    ['os', 'pkg', 'pkg.util']
    """
    try:
        tree = ast.parse(path.read_bytes())
    except (OSError, SyntaxError, ValueError):
        return set()
    base = module.split(".") if is_package else module.split(".")[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = base[: len(base) - node.level + 1] if node.level <= len(base) else []
                root = ".".join([*parent, *(node.module.split(".") if node.module else [])])
            else:
                root = node.module or ""
            if root:
                found.add(root)
                found.update(f"{root}.{a.name}" for a in node.names if a.name != "*")
    return found
