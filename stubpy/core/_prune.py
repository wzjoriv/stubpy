"""
Orphan stubs: ``.pyi`` files under a folder target's stub tree that no module of the run produced.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .results import Report
from .targets import Plan

_SKIPPED_DIRS = ("__pycache__", "build", "dist", "node_modules")


def orphan_stubs(plan: Plan, report: Report) -> list[Path]:
    """Return the ``.pyi`` files under each folder target's stub tree that the run did not produce.

    A stub tracked by git is never an orphan (it may be hand-written), nor is one in a hidden or build
    folder. Folder targets only: a single file or module target has no tree to clean.

    Parameters
    ----------
    plan : Plan
        The run's jobs; groups with a folder root are scanned.
    report : Report
        The finished run; every stub it wrote, compared or kept counts as produced.

    Returns
    -------
    list of pathlib.Path
        The orphan stubs, sorted.
    """
    produced = {r.output.resolve() for r in report.results if r.output is not None}
    produced |= {job.output.resolve() for _, jobs in plan.groups for job in jobs}
    produced |= {job.output.resolve() for job in plan.placeholders}
    orphans: set[Path] = set()
    for root, jobs in plan.groups:
        outputs = [job.output.resolve() for job in jobs]
        if root is None or not outputs:
            continue
        tree = Path(os.path.commonpath([str(p.parent) for p in outputs]))
        if not tree.is_dir():
            continue
        tracked = _git_tracked(tree)
        if tracked is None:
            continue
        for stub in tree.rglob("*.pyi"):
            relative = stub.relative_to(tree).parts[:-1]
            if any(part.startswith(".") or part in _SKIPPED_DIRS for part in relative):
                continue
            resolved = stub.resolve()
            if resolved not in produced and resolved not in tracked:
                orphans.add(resolved)
    return sorted(orphans)


def _git_tracked(folder: Path) -> set[Path] | None:
    """The files under *folder* that git tracks; empty outside a repository; ``None`` when git cannot tell.

    ``None`` (git failing or timing out inside a repository) means nothing under *folder* may be pruned:
    a stub git would have protected must never be deleted because the check itself failed.
    """
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=folder, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None
    except (OSError, subprocess.SubprocessError):
        return None if _inside_repository(folder) else set()
    if out.returncode != 0:
        return set() if b"not a git repository" in out.stderr.lower() else None
    return {(folder / name).resolve() for name in out.stdout.decode("utf-8", "replace").split("\0") if name}


def _inside_repository(folder: Path) -> bool:
    """True when *folder* or a parent holds a ``.git`` (git cannot be run to ask)."""
    return any((parent / ".git").exists() for parent in (folder, *folder.parents))
