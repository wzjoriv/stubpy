"""``dev.py build`` / ``dev.py release``: executables with PyInstaller (the user data next to an earlier build
kept), and a zip of them for sharing without anyone's own data.

    [tool.devkit.build]
    spec = "packaging/mypkg.spec"
    dist = "dist/mypkg"                      # what the spec builds
    keep = ["mypkg.toml", "cache"]           # user files next to the executables: kept through a build, left out of a release
    zip = "mypkg-{version}-{os}.zip"         # {version}: [project] version, or `version` below; {os}: windows / macos / linux
    version = "mypkg:__version__"            # where the version is when pyproject does not say it
    before = ["i18n.translations:compile_all"]   # run before PyInstaller (--no-steps skips them)
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import typer

from .config import ConfigError, pyproject, root_path, typed
from .hooks import hooks
from .paths import ROOT, shown

__all__ = ["register"]

WHERE = "tool.devkit.build"
OS_NAMES = {"win32": "windows", "darwin": "macos"}


def _version(spec: str) -> str:
    version = pyproject().get("project", {}).get("version")
    if version:
        return str(version)
    module, _, attr = spec.partition(":")
    if not module or not attr:
        raise ConfigError(f"[{WHERE}] version {spec!r}: give 'module:attribute' (no [project] version)")
    return str(getattr(importlib.import_module(module), attr))


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``build`` and ``release`` commands, configured by ``[tool.devkit.build]`` (``cfg``)."""
    if "spec" not in cfg or "dist" not in cfg:
        raise ConfigError(f"[{WHERE}] needs spec and dist")
    spec = root_path(typed(cfg, "spec", str, "", WHERE))
    dist = Path(root_path(typed(cfg, "dist", str, "", WHERE)))
    keep = typed(cfg, "keep", list, [], WHERE)
    zip_name = typed(cfg, "zip", str, f"{dist.name}-{{version}}-{{os}}.zip", WHERE)
    version = typed(cfg, "version", str, "", WHERE)
    before = typed(cfg, "before", list, [], WHERE)
    aside = dist.parent.parent / "build" / "kept-user-data"

    def build(steps: bool = typer.Option(True, "--steps/--no-steps", help="Run the project's steps first.")) -> None:
        """Build the executables (the user data next to an earlier build is kept)."""
        for _name, fn in hooks(before, WHERE) if steps else []:
            fn()
        if aside.exists():
            typer.echo(f"{aside} exists (data from an interrupted build?): move it back into {dist} first.", err=True)
            raise typer.Exit(1)
        kept = [n for n in keep if (dist / n).exists()]
        aside.mkdir(parents=True)
        for name in kept:
            shutil.move(str(dist / name), str(aside / name))
        try:
            code = subprocess.call([sys.executable, "-m", "PyInstaller", "--noconfirm", spec], cwd=ROOT)
        finally:
            dist.mkdir(parents=True, exist_ok=True)
            for name in kept:
                shutil.move(str(aside / name), str(dist / name))
            aside.rmdir()
        typer.echo(f"kept: {', '.join(kept) or 'nothing'}")
        raise typer.Exit(code)

    def release() -> None:
        """Zip the built executables for sharing, without the user files (`keep`)."""
        if not dist.is_dir():
            typer.echo(f"no {shown(dist)}: run python scripts/dev.py build first", err=True)
            raise typer.Exit(1)
        target = dist.parent / zip_name.format(version=_version(version), os=OS_NAMES.get(sys.platform, sys.platform))
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for folder, dirs, files in os.walk(dist):
                if Path(folder) == dist:
                    dirs[:] = [d for d in dirs if d not in keep]
                    files = [f for f in files if f not in keep]
                for f in files:
                    path = Path(folder, f)
                    z.write(path, Path(dist.name, path.relative_to(dist)))
        typer.echo(f"{shown(target)} ({target.stat().st_size / 2 ** 20:.0f} MB)")

    app.command("build")(build)
    app.command("release")(release)
