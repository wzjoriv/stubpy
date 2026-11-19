"""
Named test tiers: pytest with fixed arguments, memory-capped, low priority, logged to a file.
"""

from __future__ import annotations

import datetime as _dt
import functools
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import ConfigError, root_path, typed
from .paths import ROOT, shown

__all__ = ["Tier", "tiers", "command", "run", "register"]

WHERE = "tool.devkit.tiers"
REQUIRES: tuple[str, ...] = ("pytest>=7.0",)
EXTERNAL: tuple[str, ...] = ()
_SETTINGS = ("default", "log_dir", "memory_max", "nice", "omp_threads", "runner")


@dataclass(frozen=True)
class Tier:
    """One named tier, its defaults resolved."""

    name: str
    help: str = ""
    args: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    memory_max: str = ""
    nice: int = 10
    omp_threads: int = 0
    env: dict[str, str] = field(default_factory=dict)
    runner: list[str] = field(default_factory=lambda: ["{python}", "-m", "pytest"])


def tiers(cfg: dict[str, Any]) -> dict[str, Tier]:
    """The tiers of ``[tool.devkit.tiers]`` (``cfg``), each with the table's defaults filled in."""
    defaults = {k: cfg[k] for k in ("memory_max", "nice", "omp_threads", "runner") if k in cfg}
    out: dict[str, Tier] = {}
    for name, table in cfg.items():
        if name in _SETTINGS:
            continue
        if not isinstance(table, dict):
            raise ConfigError(f"[{WHERE}] {name!r}: unknown setting (tiers are tables)")
        where = f"{WHERE}.{name}"
        merged = {**defaults, **table}
        out[name] = Tier(
            name=name,
            help=typed(merged, "help", str, "", where),
            args=[str(a) for a in typed(merged, "args", list, [], where)],
            parts=[str(p) for p in typed(merged, "parts", list, [], where)],
            memory_max=typed(merged, "memory_max", str, "", where),
            nice=typed(merged, "nice", int, 10, where),
            omp_threads=typed(merged, "omp_threads", int, 0, where),
            env={str(k): str(v) for k, v in typed(merged, "env", dict, {}, where).items()},
            runner=[str(a) for a in typed(merged, "runner", list, ["{python}", "-m", "pytest"], where)],
        )
    for t in out.values():
        if bool(t.args) == bool(t.parts):
            raise ConfigError(f"[{WHERE}.{t.name}] needs either args or parts")
        for p in t.parts:
            if p not in out or out[p].parts:
                raise ConfigError(f"[{WHERE}.{t.name}] part {p!r} is not a tier with args")
    return out


@functools.cache
def _systemd_scope_works() -> bool:
    """Whether ``systemd-run --user --scope`` can start a process here (a user manager is running)."""
    if shutil.which("systemd-run") is None:
        return False
    probe = subprocess.run(["systemd-run", "--user", "--scope", "-q", "true"], capture_output=True)
    return probe.returncode == 0


def command(tier: Tier, extra: list[str], cap: bool = True) -> list[str]:
    """The argv of one run of ``tier`` (a tier with ``args``) with ``extra`` pytest arguments appended."""
    argv = [sys.executable if a == "{python}" else a for a in tier.runner] + tier.args + extra
    if tier.nice and shutil.which("nice"):
        argv = ["nice", "-n", str(tier.nice), *argv]
    if cap and tier.memory_max and _systemd_scope_works():
        argv = ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={tier.memory_max}", *argv]
    return argv


def environment(tier: Tier, keep_pythonpath: bool = False) -> dict[str, str]:
    """The run's environment: this one without ``PYTHONPATH`` (unless ``keep_pythonpath``; a tier's own
    ``env = {PYTHONPATH = ...}`` sets one), with ``OMP_NUM_THREADS`` and the tier's ``env``."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH" or keep_pythonpath}
    if tier.omp_threads:
        env["OMP_NUM_THREADS"] = str(tier.omp_threads)
    env.update(tier.env)
    return env


def _env_note(tier: Tier, env: dict[str, str]) -> str:
    """The run's environment changes, for the log and ``--dry-run``."""
    path = f"PYTHONPATH={env['PYTHONPATH']}" if "PYTHONPATH" in env else "PYTHONPATH unset"
    return " ".join([path, *(f"{k}={env[k]}" for k in ("OMP_NUM_THREADS", *tier.env) if k in env and k != "PYTHONPATH")])


def run(tier: Tier, extra: list[str], log_dir: Path, cap: bool = True, keep_pythonpath: bool = False) -> int:
    """Run ``tier`` (with ``args``) from the repository root, its output both shown and written to a new log in
    ``log_dir``; pytest's exit code."""
    argv, env = command(tier, extra, cap), environment(tier, keep_pythonpath)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{tier.name}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    start = time.monotonic()
    with open(log, "w", encoding="utf-8") as out:
        out.write(f"# {shlex.join(argv)}\n# cwd {ROOT}; {_env_note(tier, env)}\n")
        out.flush()
        proc = subprocess.Popen(
            argv,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                out.write(line)
            rc = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            rc = proc.wait()
        out.write(f"# exit {rc} after {time.monotonic() - start:.0f} s\n")
    typer.echo(f"── {tier.name}: exit {rc} in {time.monotonic() - start:.0f} s, log {shown(log)}")
    return rc


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``test`` command to ``app``, configured by ``[tool.devkit.tiers]`` (``cfg``)."""
    table = tiers(cfg)
    default = typed(cfg, "default", str, next(iter(table), ""), WHERE)
    if table and default not in table:
        raise ConfigError(f"[{WHERE}] default {default!r} is not a tier")
    log_dir = Path(root_path(typed(cfg, "log_dir", str, "build/test-logs", WHERE)))
    listing = "\n\n".join(
        f"{t.name}: {t.help or ''} ({'parts ' + ', '.join(t.parts) if t.parts else shlex.join(t.args)})"
        for t in table.values()
    )

    def test(
        tier: Annotated[str, typer.Argument(help="Tier name (see below).")] = default,
        extra: Annotated[list[str] | None, typer.Argument(help="More pytest arguments, after --.")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the commands, run nothing.")] = False,
        cap: Annotated[bool, typer.Option("--cap/--no-cap", help="Memory cap via systemd-run.")] = True,
        keep_pythonpath: Annotated[bool, typer.Option(
            "--keep-pythonpath", help="Keep your PYTHONPATH (test against another checkout of a dependency).")] = False,
    ) -> None:
        if tier not in table:
            typer.echo(f"unknown tier {tier!r}; tiers: {', '.join(table)}", err=True)
            raise typer.Exit(2)
        steps = [table[p] for p in table[tier].parts] or [table[tier]]
        first_failure = 0
        for step in steps:
            if dry_run:
                note = _env_note(step, environment(step, keep_pythonpath))
                typer.echo(f"{step.name} ({note}): {shlex.join(command(step, extra or [], cap))}")
                continue
            rc = run(step, extra or [], log_dir, cap, keep_pythonpath)
            first_failure = first_failure or rc
        raise typer.Exit(first_failure)

    test.__doc__ = (
        f"Run a test tier (default {default}), memory-capped and logged to "
        f"{shown(log_dir)}.\n\n"
        f"Tiers:\n\n{listing}"
    )
    app.command(
        "test",
        short_help=f"Run a test tier (default {default}): memory-capped, logged.",
        context_settings={"ignore_unknown_options": True},
    )(test)
