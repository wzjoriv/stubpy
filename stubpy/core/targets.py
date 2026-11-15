"""Target resolution: turn files, folders, globs and dotted module names into module files and stub paths.

A module file is a ``.py`` source or a compiled extension (``.pyd`` / ``.so``).
Sources may sit inside a zip archive (``zipimport``, Pyodide's standard
library); their paths are virtual and only read through :mod:`stubpy.analysis.vfs`.
"""
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
from stubpy.analysis import vfs
from stubpy.compiled.detect import is_compiled_module, is_current_abi, is_extension_file, module_stem
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
    """One module to stub: its source file, the stub path, and whether the user named it directly."""
    source: Path
    output: Path
    explicit: bool = True


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
    if vfs.is_file(init):
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
        if out is None and not t.path.exists():
            raise ValueError(f"{t.path} is inside an archive; give an output folder for its stubs")
        files = _folder_files(t.path, config.exclude) if t.is_dir else [t.path]
        jobs = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            stub = stub_path(f) if out is None else out.resolve() / stub_path(f.relative_to(t.anchor))
            jobs.append(Job(f, stub, explicit=not t.is_dir))
        plan.groups.append((t.path if t.is_dir else None, jobs))
    if out is not None:
        plan.placeholders = _placeholders(targets, plan, out.resolve())
    return plan


def stub_path(path: Path) -> Path:
    """The stub of a module file: ``a/b.py`` and ``a/b.cp311-win_amd64.pyd`` both give ``a/b.pyi``."""
    return path.with_name(module_stem(path) + STUB_SUFFIX)


def is_module_file(path: Path) -> bool:
    """True for a ``.py`` source or an extension module file."""
    return path.suffix == SOURCE_SUFFIX or is_extension_file(path)


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
                if not vfs.is_file(folder / "__init__.py"):
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
        sources = [Path(m) for m in matches if Path(m).is_dir() or is_module_file(Path(m))]
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
    if not vfs.exists(path):
        raise FileNotFoundError(f"No such file or folder: {path}")
    if vfs.is_dir(path):
        anchor = _import_root(path) if vfs.is_file(path / "__init__.py") else path
        return Target(path, True, anchor)
    if not is_module_file(path):
        raise ValueError(f"{path} is not a Python source file (.py) or an extension module (.pyd / .so)")
    return Target(path, False, _import_root(path.parent))


def _module_target(name: str) -> Target:
    """Return the :class:`Target` of a module or package named *name*, importable from ``sys.path`` or the working folder."""
    before = set(sys.modules)
    saved_path = list(sys.path)
    if "" not in sys.path and os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())
    try:
        spec = importlib.util.find_spec(name)
    except (Exception, SystemExit) as exc:
        raise ModuleNotFoundError(f"Cannot resolve module {name!r}: {type(exc).__name__}: {exc}") from exc
    finally:
        sys.path[:] = saved_path
        _drop_source_modules(set(sys.modules) - before, name.partition(".")[0])
    if spec is None:
        raise ModuleNotFoundError(f"No module named {name!r}")
    origin = spec.origin
    locations = list(spec.submodule_search_locations or [])
    if origin and origin.endswith(SOURCE_SUFFIX):
        return _path_target(Path(origin).parent if locations else Path(origin))
    if origin and is_extension_file(origin) and Path(origin).is_file():
        return _path_target(Path(origin))
    if locations and (origin is None or origin == "namespace"):
        return _path_target(Path(locations[0]))
    raise ValueError(f"{name} has no source or extension file ({origin}); built-in modules cannot be stubbed")


def _drop_source_modules(names: set[str], top: str) -> None:
    """Forget the pure-Python modules of package *top* that resolving a dotted name imported (its parents).

    Other packages it pulled in stay loaded, and so does *top* when an
    extension module of it was loaded: neither can be safely re-imported.
    """
    mine = [n for n in names if n.partition(".")[0] == top]
    if any(is_compiled_module(sys.modules.get(n)) for n in mine):
        return
    for name in mine:
        origin = getattr(sys.modules.get(name), "__file__", None) or ""
        if origin.endswith(SOURCE_SUFFIX):
            sys.modules.pop(name, None)


def _import_root(folder: Path) -> Path:
    """Return the first folder at or above *folder* that is not a package."""
    while vfs.is_file(folder / "__init__.py") and folder.parent != folder:
        folder = folder.parent
    return folder


def _folder_files(folder: Path, exclude: tuple[str, ...]) -> list[Path]:
    """Return the module files under *folder*, sorted, minus those matching an *exclude* pattern.

    One file per module: a ``.py`` source wins over an extension of the same
    name, and an extension this interpreter imports wins over other builds.
    """
    chosen: dict[tuple[Path, str], Path] = {}
    for f in sorted(p for p in vfs.files_under(folder) if is_module_file(p)):
        rel = f.relative_to(folder).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            continue
        key = (f.parent, module_stem(f))
        if key not in chosen or _preference(f) < _preference(chosen[key]):
            chosen[key] = f
    return sorted(chosen.values())


def _preference(path: Path) -> int:
    """Lower is better: source, then an importable extension, then another build."""
    if path.suffix == SOURCE_SUFFIX:
        return 0
    return 1 if is_current_abi(path) else 2
