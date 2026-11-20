"""
Target resolution: turn files, folders, globs and dotted module names into module files and stub paths.
A module file is a ``.py`` source or a compiled extension; sources inside a zip archive are read through :mod:`stubpy.analysis.vfs`.
"""
from __future__ import annotations

import glob
import importlib.machinery
import importlib.util
import os
import sys
import sysconfig
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from stubpy._constants import GLOB_CHARS, SOURCE_SUFFIX, STUB_SUFFIX
from stubpy.analysis import vfs
from stubpy.compiled.detect import is_compiled_module, is_current_abi, is_extension_file, module_stem
from stubpy.config.options import Config

from ._exclude import excluded_by
from ._submodules import extension_member, member_stub

TargetSpec = str | os.PathLike[str]


@dataclass(frozen=True)
class Target:
    """One resolved target: a source file or a folder, and the folder its stub paths are relative to.

    Parameters
    ----------
    path : pathlib.Path
        The source file or folder.
    is_dir : bool
        Whether *path* is a folder.
    anchor : pathlib.Path
        The folder that module import paths, and so stub paths, start from.
    member : str, optional
        The attribute submodule of a compiled extension *path* (``"fft"`` for ``pkg.fft``).  Defaults to ``""``.
    """
    path: Path
    is_dir: bool
    anchor: Path
    member: str = ""


@dataclass(frozen=True)
class Job:
    """One module to stub: its source file, the stub path, and whether the user named it directly.

    Parameters
    ----------
    source : pathlib.Path
        The module file.
    output : pathlib.Path
        Where its stub is written.
    explicit : bool, optional
        ``False`` when the file was found by searching a folder.  Defaults to ``True``.
    member : str, optional
        The attribute submodule of a compiled extension *source* to stub.  Defaults to ``""``.
    """
    source: Path
    output: Path
    explicit: bool = True
    member: str = ""


@dataclass
class Plan:
    """Jobs grouped by target (each group shares a module loader rooted at ``root``) plus placeholders.

    Parameters
    ----------
    groups : list of tuple of (pathlib.Path or None, list of Job), optional
        One ``(root, jobs)`` pair per target.  Defaults to an empty list.
    placeholders : list of Job, optional
        ``__init__.pyi`` jobs for package folders without a stub.  Defaults to an empty list.
    excluded : list of tuple of (pathlib.Path, str), optional
        Files skipped by an ``exclude`` pattern, with the pattern.  Defaults to an empty list.
    """
    groups: list[tuple[Path | None, list[Job]]] = field(default_factory=list)
    placeholders: list[Job] = field(default_factory=list)
    excluded: list[tuple[Path, str]] = field(default_factory=list)


def resolve_targets(target: TargetSpec | Iterable[TargetSpec] | None, config: Config) -> list[Target]:
    """Resolve *target* (one or several), or the config's ``targets`` and ``modules`` when it is ``None``.

    Parameters
    ----------
    target : str, os.PathLike, iterable of those, or None
        Files, folders, globs or dotted module names.
    config : Config
        Supplies ``targets`` and ``modules`` when *target* is ``None``.

    Returns
    -------
    list of Target
        The distinct targets, in the order given.

    Raises
    ------
    ValueError
        If nothing is given and nothing is configured.
    FileNotFoundError
        If a target names no existing file, folder or module.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> from stubpy.config import Config
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("")
    ...     [t.is_dir for t in resolve_targets(src, Config())]
    [False]
    """
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
    unique: dict[tuple[Path, str], Target] = {}
    for t in resolved:
        unique.setdefault((t.path, t.member), t)
    return list(unique.values())


def resolve_module_file(target: TargetSpec) -> Path:
    """Return the single ``.py`` file *target* names; a package resolves to its ``__init__.py``.

    Parameters
    ----------
    target : str or os.PathLike
        A file, a package folder, a glob matching one file, or a dotted module name.

    Returns
    -------
    pathlib.Path
        The module file.

    Raises
    ------
    TypeError
        If *target* is not a string or path.
    ValueError
        If *target* matches several paths, or is a folder without an ``__init__.py``.
    FileNotFoundError
        If *target* names nothing that exists.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("")
    ...     resolve_module_file(src).name
    'mod.py'
    """
    return module_file_and_member(target)[0]


def module_file_and_member(target: TargetSpec) -> tuple[Path, str]:
    """Return :func:`resolve_module_file` of *target* and the extension attribute submodule it names, or ``""``."""
    if not isinstance(target, (str, os.PathLike)):
        raise TypeError(f"render() takes one target, not {type(target).__name__}")
    found = _resolve(target)
    if len(found) != 1:
        raise ValueError(f"{os.fspath(target)!r} matches {len(found)} paths; render() takes exactly one module")
    t = found[0]
    if not t.is_dir:
        return t.path, t.member
    init = t.path / "__init__.py"
    if vfs.is_file(init):
        return init, ""
    raise ValueError(f"{t.path} is a folder, not a module; use generate() or check() for folders")


def plan_jobs(targets: list[Target], output: str | os.PathLike[str] | None, config: Config) -> Plan:
    """Pair every source file with its stub path.

    Without *output* stubs go next to their sources.  An *output* ending in
    ``.pyi`` is the stub file of a single file target.  Any other *output*
    is a stub root: each module lands at its import path beneath it, and
    every package folder on the way gets an ``__init__.pyi``.

    Parameters
    ----------
    targets : list of Target
        The resolved targets.
    output : str or os.PathLike or None
        The stub root or single ``.pyi`` file; ``None`` for next to the sources.
    config : Config
        Supplies the ``exclude`` patterns.

    Returns
    -------
    Plan
        The jobs to run, the placeholder jobs and the excluded files.

    Raises
    ------
    ValueError
        If *output* is a ``.pyi`` file but the target is not a single file, or
        a target inside an archive has no output folder.

    Examples
    --------
    >>> import pathlib, tempfile
    >>> from stubpy.config import Config
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     src = pathlib.Path(folder) / "mod.py"
    ...     _ = src.write_text("")
    ...     plan = plan_jobs(resolve_targets(src, Config()), None, Config())
    ...     [job.output.name for _, jobs in plan.groups for job in jobs]
    ['mod.pyi']
    """
    plan = Plan()
    out = Path(output) if output is not None else None
    if out is not None and out.suffix == STUB_SUFFIX:
        if len(targets) != 1 or targets[0].is_dir:
            raise ValueError(f"Output {out} is a .pyi file, so the target must be a single .py file")
        plan.groups.append((None, [Job(targets[0].path, out.resolve())]))
        return plan

    seen: set[tuple[Path, str]] = set()
    for t in targets:
        if out is None and not t.path.exists():
            raise ValueError(f"{t.path} is inside an archive; give an output folder for its stubs")
        files = _folder_files(t.path, config.exclude_patterns, plan.excluded) if t.is_dir else [t.path]
        jobs = []
        for f in files:
            if (f, t.member) in seen:
                continue
            seen.add((f, t.member))
            stub = stub_path(f) if out is None else out.resolve() / stub_path(f.relative_to(t.anchor))
            jobs.append(Job(f, member_stub(stub, t.member) if t.member else stub, explicit=not t.is_dir,
                            member=t.member))
        plan.groups.append((t.path if t.is_dir else None, jobs))
    if out is not None:
        plan.placeholders = _placeholders(targets, plan, out.resolve())
    return plan


def stub_path(path: Path) -> Path:
    """The stub of a module file: ``a/b.py`` and ``a/b.cp311-win_amd64.pyd`` both give ``a/b.pyi``.

    Parameters
    ----------
    path : pathlib.Path
        A source or extension module file.

    Returns
    -------
    pathlib.Path
        The sibling path with the platform tags and suffix replaced by ``.pyi``.

    Examples
    --------
    >>> from pathlib import Path
    >>> stub_path(Path("a/b.py")).as_posix()
    'a/b.pyi'
    >>> stub_path(Path("a/b.cp311-win_amd64.pyd")).as_posix()
    'a/b.pyi'
    """
    return path.with_name(module_stem(path) + STUB_SUFFIX)


def is_module_file(path: Path) -> bool:
    """True for a ``.py`` source, a Cython ``.pyx`` source or an extension module file.

    Parameters
    ----------
    path : pathlib.Path
        The file to classify, by name.

    Returns
    -------
    bool
        Whether stubpy can stub the file.

    Examples
    --------
    >>> from pathlib import Path
    >>> is_module_file(Path("mod.py")), is_module_file(Path("notes.txt"))
    (True, False)
    """
    return path.suffix in (SOURCE_SUFFIX, ".pyx") or is_extension_file(path)


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
        raise ValueError(f"{path} is not a Python source (.py), a Cython source (.pyx) or an extension module (.pyd / .so)")
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
        member = extension_member(name)
        if member is not None:
            return Target(member[0], False, _import_root(member[0].parent), member[1])
        raise ModuleNotFoundError(f"Cannot resolve module {name!r}: {type(exc).__name__}: {exc}") from exc
    finally:
        sys.path[:] = saved_path
        _drop_source_modules(set(sys.modules) - before, name.partition(".")[0])
    if spec is None:
        raise ModuleNotFoundError(f"No module named {name!r}")
    origin = spec.origin
    locations = list(spec.submodule_search_locations or [])
    if not (origin and vfs.is_file(origin)) and not (locations and origin in (None, "namespace")):
        found = _stdlib_file(name, spec)
        if found is not None:
            return _path_target(found.parent if found.name == "__init__.py" else found)
    if origin and origin.endswith(SOURCE_SUFFIX):
        return _path_target(Path(origin).parent if locations else Path(origin))
    if origin and is_extension_file(origin) and Path(origin).is_file():
        return _path_target(Path(origin))
    if locations and (origin is None or origin == "namespace"):
        return _path_target(Path(locations[0]))
    raise ValueError(f"{name} is built into the interpreter and has no source or extension file anywhere ({origin}); "
                     "it cannot be stubbed")


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


def _folder_files(folder: Path, exclude: tuple[str, ...], skipped: list[tuple[Path, str]]) -> list[Path]:
    """Return the module files under *folder*, sorted, minus those an *exclude* pattern matches (added to *skipped*).

    One file per module: a ``.py`` source wins over an extension of the same
    name, and an extension this interpreter imports wins over other builds.
    """
    chosen: dict[tuple[Path, str], Path] = {}
    for f in sorted(p for p in vfs.files_under(folder) if is_module_file(p)):
        rel = f.relative_to(folder).as_posix()
        pattern = excluded_by(rel, exclude)
        if pattern is not None:
            skipped.append((f, pattern))
            continue
        key = (f.parent, module_stem(f))
        if key not in chosen or _preference(f) < _preference(chosen[key]):
            chosen[key] = f
    return sorted(chosen.values())


def _preference(path: Path) -> int:
    """Lower is better: source, then an importable extension, then a Cython source, then another build."""
    if path.suffix == SOURCE_SUFFIX:
        return 0
    if path.suffix == ".pyx":
        return 2
    return 1 if is_current_abi(path) else 3


def _stdlib_file(name: str, spec: importlib.machinery.ModuleSpec) -> Path | None:
    """The source of a frozen module (``origin="frozen"``): the frozen loader's file, else the stdlib folder's."""
    candidates: list[Path] = []
    filename = getattr(spec.loader_state, "filename", None)
    if isinstance(filename, str):
        candidates.append(Path(filename))
    module = sys.modules.get(name)
    if isinstance(getattr(module, "__file__", None), str):
        candidates.append(Path(module.__file__))
    for key in ("stdlib", "platstdlib"):
        folder = Path(sysconfig.get_paths().get(key, "")).joinpath(*name.split("."))
        candidates += [folder / "__init__.py", folder.with_name(folder.name + SOURCE_SUFFIX)]
    return next((c for c in candidates if c.suffix == SOURCE_SUFFIX and vfs.is_file(c)), None)
