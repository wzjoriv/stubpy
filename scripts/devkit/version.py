"""
Show, bump or set the project version in __version__ and in the extra files that repeat it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import ConfigError, root_path, typed
from .paths import shown

__all__ = ["parse", "bump", "register"]

WHERE = "tool.devkit.version"
REQUIRES: tuple[str, ...] = ()
EXTERNAL: tuple[str, ...] = ()
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_ASSIGN = re.compile(r"""^(?P<head>[ \t]*__version__[ \t]*(?::[^=\n]+)?=[ \t]*)(?P<q>["'])(?P<v>[^"'\n]*)(?P=q)""", re.M)
_KINDS = ("major", "minor", "patch")
Dry = Annotated[bool, typer.Option("--dry-run", help="Show the changes, write nothing.")]


def parse(text: str) -> tuple[int, int, int]:
    """``text`` ("1.2.3") as a tuple; a dirty, pre-release or partial version raises ``ValueError``."""
    if not _VERSION.fullmatch(text):
        raise ValueError(f"{text!r} is not a plain X.Y.Z version (no v prefix, pre-release or local part)")
    major, minor, patch = (int(p) for p in text.split("."))
    return major, minor, patch


def bump(current: str, kind: str) -> str:
    """``current`` with its ``kind`` (major, minor or patch) raised and the lower parts reset."""
    major, minor, patch = parse(current)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump {kind!r}; use one of {', '.join(_KINDS)}")


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``version`` command group, configured by ``[tool.devkit.version]`` (``cfg``)."""
    if "file" not in cfg:
        raise ConfigError(f"[{WHERE}] needs file (the module holding __version__)")
    main = Path(root_path(typed(cfg, "file", str, "", WHERE)))
    also = typed(cfg, "also", list, [], WHERE)
    tag_format = typed(cfg, "tag", str, "v{version}", WHERE)
    for i, item in enumerate(also):
        if not (isinstance(item, dict) and isinstance(item.get("file"), str)
                and isinstance(item.get("pattern"), str) and "{version}" in item["pattern"]):
            raise ConfigError(f"[{WHERE}] also[{i}] needs file and a pattern containing {{version}}")

    def fail(message: str) -> typer.Exit:
        typer.echo(message, err=True)
        return typer.Exit(2)

    def text_of(path: Path) -> str:
        if not path.is_file():
            raise fail(f"{shown(path)}: no such file")
        return path.read_bytes().decode("utf-8")  # bytes: line endings stay as they are

    def current() -> str:
        found = _ASSIGN.search(text_of(main))
        if not found:
            raise fail(f'{shown(main)}: no __version__ = "..." line')
        return found["v"]

    def apply(new: str, dry_run: bool) -> None:
        old = current()
        try:
            parse(old)
            parse(new)
        except ValueError as exc:
            raise fail(str(exc)) from exc
        if new == old:
            raise fail(f"already at {new}")
        source = text_of(main)
        plan = [(main, _ASSIGN.sub(lambda m: f"{m['head']}{m['q']}{new}{m['q']}", source, count=1))]
        for item in also:
            path = Path(root_path(item["file"]))
            text = text_of(path)
            before = item["pattern"].replace("{version}", old)
            if before not in text:
                raise fail(f"{shown(path)}: {before!r} not found (is it at {old}?)")
            plan.append((path, text.replace(before, item["pattern"].replace("{version}", new))))
        for path, updated in plan:
            typer.echo(f"{shown(path)}: {old} -> {new}")
            if not dry_run:
                path.write_bytes(updated.encode("utf-8"))
        if dry_run:
            typer.echo("dry run: nothing written")
        else:
            tag = tag_format.replace("{version}", new)
            typer.echo(f'tag it:  git tag -a {tag} -m "{tag}" && git push origin {tag}')

    group = typer.Typer(help="Show, bump or set the project version.", no_args_is_help=True, add_completion=False,
                        context_settings={"help_option_names": ["-h", "--help"]})
    @group.command("show")
    def show() -> None:
        """Print the current version."""
        typer.echo(current())

    @group.command("bump")
    def bump_command(kind: Annotated[str, typer.Argument(help="major, minor or patch.")], dry_run: Dry = False) -> None:
        """Raise the major, minor or patch number (lower parts reset to 0)."""
        if kind not in _KINDS:
            raise fail(f"{kind!r}: use one of {', '.join(_KINDS)}")
        try:
            new = bump(current(), kind)
        except ValueError as exc:
            raise fail(str(exc)) from exc
        apply(new, dry_run)

    @group.command("set")
    def set_command(version: Annotated[str, typer.Argument(help="The new X.Y.Z.")], dry_run: Dry = False) -> None:
        """Set an exact X.Y.Z version."""
        apply(version, dry_run)

    app.add_typer(group, name="version")
