"""Target resolution: turn files, folders, globs and dotted module names into source files and stub paths."""
from __future__ import annotations

import fnmatch
import glob
import importlib.util
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from stubpy._constants import GLOB_CHARS, SOURCE_SUFFIX, STUB_SUFFIX
from stubpy.config.options import Config

TargetSpec = str | os.PathLike[str]


@dataclass(frozen=True)
class Target:
    """One resolved target: a source file or a folder, and the folder its stub paths are relative to."""
    path: Path
    is_dir: bool
    anchor: Path


@dataclass(frozen=True)
class Job:
    """One module to stub: its source file and the stub path."""
    source: Path
    output: Path


@dataclass
class Plan:
    """Jobs grouped by target (each group shares a module loader rooted at ``root``) plus placeholders."""
    groups: list[tuple[Path | None, list[Job]]] = field(default_factory=list)
    placeholders: list[Job] = field(default_factory=list)


def resolve_targets(target: TargetSpec | Iterable[TargetSpec] | None, config: Config) -> list[Target]:
    """Resolve *target* (one or several), or the config's ``targets`` and ``modules`` when it is ``None``."""
    if target is None:
        if not config.targets and not config.modules:
            raise ValueError("No target given and no 'targets' or 'modules' configured")
        resolved = [t for spec in config.targets for t in _resolve(spec, as_module=False)]
        resolved += [_module_target(name) for name in config.modules]
    else:
        specs = [target] if isinstance(target, (str, os.PathLike)) else list(target)
        if not specs:
            raise ValueError("No target given")
        resolved = [t for spec in specs for t in _resolve(spec)]
    unique: dict[Path, Target] = {}
    for t in resolved:
        unique.setdefault(t.path, t)
    return list(unique.values())


def resolve_module_file(target: TargetSpec) -> Path:
    """Return the single ``.py`` file *target* names; a package resolves to its ``__init__.py``."""
    if not isinstance(target, (str, os.PathLike)):
        raise TypeError(f"render() takes one target, not {type(target).__name__}")
    found = _resolve(target)
    if len(found) != 1:
        raise ValueError(f"{os.fspath(target)!r} matches {len(found)} paths; render() takes exactly one module")
    t = found[0]
    if not t.is_dir:
        return t.path
    init = t.path / "__init__.py"
    if init.is_file():
        return init
    raise ValueError(f"{t.path} is a folder, not a module; use generate() or check() for folders")


def plan_jobs(targets: list[Target], output: str | os.PathLike[str] | None, config: Config) -> Plan:
    """Pair every source file with its stub path.

    Without *output* stubs go next to their sources.  An *output* ending in
    ``.pyi`` is the stub file of a single file target.  Any other *output*
    is a stub root: each module lands at its import path beneath it, and
    every package folder on the way gets an ``__init__.pyi``.
    """
    plan = Plan()
    out = Path(output) if output is not None else None
    if out is not None and out.suffix == STUB_SUFFIX:
        if len(targets) != 1 or targets[0].is_dir:
            raise ValueError(f"Output {out} is a .pyi file, so the target must be a single .py file")
        plan.groups.append((None, [Job(targets[0].path, out.resolve())]))
        return plan

    seen: set[Path] = set()
    for t in targets:
        files = _folder_files(t.path, config.exclude) if t.is_dir else [t.path]
        jobs = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            stub = f.with_suffix(STUB_SUFFIX) if out is None else out.resolve() / f.relative_to(t.anchor).with_suffix(STUB_SUFFIX)
            jobs.append(Job(f, stub))
        plan.groups.append((t.path if t.is_dir else None, jobs))
    if out is not None:
        plan.placeholders = _placeholders(targets, plan, out.resolve())
    return plan


def _placeholders(targets: list[Target], plan: Plan, out: Path) -> list[Job]:
    """Return an ``__init__.pyi`` job for each package folder in the stub tree that gets no stub of its own."""
    written = {job.output for _, jobs in plan.groups for job in jobs}
    anchors = {t.path if t.is_dir else t.path.parent: t.anchor for t in targets}
    found: dict[Path, Job] = {}
    for _, jobs in plan.groups:
        for job in jobs:
            anchor = next((a for folder, a in anchors.items() if folder in (job.source.parent, *job.source.parents)), None)
            if anchor is None:
                continue
            for folder in (job.source.parent, *job.source.parent.parents):
                if folder == anchor or anchor not in folder.parents:
                    break
                if not (folder / "__init__.py").is_file():
                    continue
                init = out / folder.relative_to(anchor) / f"__init__{STUB_SUFFIX}"
                if init not in written:
                    found.setdefault(init, Job(folder, init))
    return list(found.values())


def _resolve(spec: TargetSpec, as_module: bool | None = None) -> list[Target]:
    """Resolve one target spec; ``as_module=None`` auto-detects paths, globs and dotted names."""
    if isinstance(spec, os.PathLike):
        return [_path_target(Path(spec))]
    if not isinstance(spec, str):
        raise TypeError(f"A target must be a str or os.PathLike, not {type(spec).__name__}")
    if as_module:
        return [_module_target(spec)]
    if any(c in spec for c in GLOB_CHARS):
        matches = sorted(glob.glob(spec, recursive=True))
        sources = [Path(m) for m in matches if Path(m).is_dir() or Path(m).suffix == SOURCE_SUFFIX]
        if not sources:
            raise FileNotFoundError(f"No Python files or folders match {spec!r}")
        return [_path_target(p) for p in sources]
    path = Path(spec)
    if path.exists():
        return [_path_target(path)]
    if as_module is None and _looks_like_module(spec):
        return [_module_target(spec)]
    raise FileNotFoundError(f"No such file, folder or module: {spec!r}")


def _looks_like_module(spec: str) -> bool:
    return not spec.endswith((SOURCE_SUFFIX, STUB_SUFFIX)) and all(p.isidentifier() for p in spec.split("."))


def _path_target(path: Path) -> Target:
    """Return the :class:`Target` for an existing file or folder."""
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file or folder: {path}")
    if path.is_dir():
        anchor = _import_root(path) if (path / "__init__.py").is_file() else path
        return Target(path, True, anchor)
    if path.suffix != SOURCE_SUFFIX:
        raise ValueError(f"{path} is not a Python source file (.py)")
    return Target(path, False, _import_root(path.parent))


def _module_target(name: str) -> Target:
    """Return the :class:`Target` of an importable module or package named *name*."""
    before = set(sys.modules)
    try:
        spec = importlib.util.find_spec(name)
    except (Exception, SystemExit) as exc:
        raise ModuleNotFoundError(f"Cannot resolve module {name!r}: {type(exc).__name__}: {exc}") from exc
    finally:
        _drop_source_modules(set(sys.modules) - before)
    if spec is None:
        raise ModuleNotFoundError(f"No module named {name!r}")
    origin = spec.origin
    locations = list(spec.submodule_search_locations or [])
    if origin and origin.endswith(SOURCE_SUFFIX):
        return _path_target(Path(origin).parent if locations else Path(origin))
    if locations and (origin is None or origin == "namespace"):
        return _path_target(Path(locations[0]))
    raise ValueError(
        f"{name} has no Python source ({origin}); stubbing compiled or built-in modules is not supported yet"
    )


def _drop_source_modules(names: set[str]) -> None:
    """Forget the pure-Python modules that resolving a dotted name imported (its parent packages)."""
    for name in names:
        origin = getattr(sys.modules.get(name), "__file__", None) or ""
        if origin.endswith(SOURCE_SUFFIX):
            sys.modules.pop(name, None)


def _import_root(folder: Path) -> Path:
    """Return the first folder at or above *folder* that is not a package."""
    while (folder / "__init__.py").is_file() and folder.parent != folder:
        folder = folder.parent
    return folder


def _folder_files(folder: Path, exclude: tuple[str, ...]) -> list[Path]:
    """Return the ``.py`` files under *folder*, sorted, minus those matching an *exclude* pattern."""
    files = []
    for f in sorted(folder.rglob(f"*{SOURCE_SUFFIX}")):
        rel = f.relative_to(folder).as_posix()
        if not any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            files.append(f)
    return files
