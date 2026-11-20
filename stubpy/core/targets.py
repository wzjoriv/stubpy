"""
Target resolution: turn files, folders, globs and dotted module names into module files and stub paths.
A module file is a ``.py`` source or a compiled extension; sources inside a zip archive are read through :mod:`stubpy.analysis.vfs`.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from stubpy._constants import STUB_SUFFIX
from stubpy.analysis import vfs
from stubpy.compiled.detect import module_stem
from stubpy.config.options import Config

from ._submodules import member_stub
from ._target_models import Job, Plan, Target, TargetSpec
from ._target_specs import _folder_files, _module_target, _resolve


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
