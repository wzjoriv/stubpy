"""
The resolved-target, job and plan records shared by target resolution and the pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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
