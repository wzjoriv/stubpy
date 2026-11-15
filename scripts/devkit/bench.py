"""Interleaved A/B benchmarks: one benchmark command run against two checkouts, alternating A, B, A, B, ...
so drift on the machine (heat, other load) hits both alike; best-of per key and the B/A ratios.

    python scripts/dev.py bench ../base . -- {python} bench_me.py --size 1000
    python scripts/dev.py bench main HEAD --rounds 7 -- {python} -m mypkg.bench

A and B are folders (another clone or worktree, already built) or git refs, checked out into a temporary
worktree and built there with ``build`` (below) and removed afterwards. Each run starts in the repository root
(so both sides run the *same* benchmark code) with ``PYTHONPATH`` = the checkout (only it, unless
``keep_pythonpath``) and ``DEVKIT_CHECKOUT`` = the checkout, for tools that put a checkout on ``sys.path``
themselves. In the command, ``{python}`` is this interpreter and ``{checkout}`` the side's folder.

The contract: the benchmark prints one line per measurement, ``<key>: <number> <unit>``, unit one of ns, us,
µs, ms, s (shown in ms; lower is better), e.g. ``plan N=256: 41.3 ms``. Other lines are ignored. A project
whose tools print otherwise sets ``pattern``, a regular expression with the groups ``key``, ``value`` and
optionally ``unit`` (ms when absent)::

    [tool.devkit.bench]
    rounds = 5                                         # A/B pairs
    build = ["{python}", "setup.py", "build_ext", "--inplace"]   # run in a ref's temporary worktree
    keep_pythonpath = false
    omp_threads = 4                                    # OMP_NUM_THREADS of the runs (0: inherit)
    pattern = '^\\s*(?P<key>[^:]+?)\\s*:\\s*(?P<value>[-+0-9.eE]+)\\s*(?P<unit>ms)\\s*$'
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import ConfigError, typed
from .paths import ROOT

__all__ = ["PATTERN", "parse", "checkout", "register"]

WHERE = "tool.devkit.bench"
#: The default measurement line: ``<key>: <number> <unit>``
PATTERN = r"^\s*(?P<key>[^:]+?)\s*:\s*(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>ns|us|µs|ms|s)\s*$"
_TO_MS = {"ns": 1e-6, "us": 1e-3, "µs": 1e-3, "ms": 1.0, "s": 1e3}


def parse(output: str, pattern: re.Pattern[str]) -> dict[str, float]:
    """The measurements (ms) in a benchmark's ``output``; a key printed twice keeps its smallest value."""
    found: dict[str, float] = {}
    for line in output.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        groups = m.groupdict()
        try:
            ms = float(groups["value"]) * _TO_MS[groups.get("unit") or "ms"]
        except (ValueError, KeyError):
            continue
        key = " ".join(groups["key"].split()).rstrip(":")  # column padding is not part of the key
        found[key] = min(ms, found.get(key, math.inf))
    return found


def _expand(argv: list[str], side: Path) -> list[str]:
    """``argv`` with ``{python}`` and ``{checkout}`` filled in."""
    return [a.replace("{python}", sys.executable).replace("{checkout}", str(side)) for a in argv]


@contextlib.contextmanager
def checkout(spec: str, build: list[str], keep: bool) -> Iterator[Path]:
    """The folder of ``spec``: itself when it is a folder, else a temporary git worktree of the ref ``spec``,
    built with ``build`` (removed on exit unless ``keep``)."""
    if Path(spec).is_dir():
        yield Path(spec).resolve()
        return
    ok = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if ok.returncode != 0:
        raise typer.BadParameter(f"{spec!r} is neither a folder nor a git ref of {ROOT}")
    folder = Path(tempfile.mkdtemp(prefix=f"devkit-bench-{re.sub(r'[^A-Za-z0-9_.-]', '_', spec)}-"))
    subprocess.run(["git", "worktree", "add", "--detach", "--quiet", str(folder), spec], cwd=ROOT, check=True)
    try:
        if build:
            typer.echo(f"building {spec} in {folder}")
            subprocess.run(_expand(build, folder), cwd=folder, check=True)
        yield folder
    finally:
        if keep:
            typer.echo(f"kept {spec} at {folder}")
        else:
            subprocess.run(["git", "worktree", "remove", "--force", str(folder)], cwd=ROOT, check=False)


def _run_once(argv: list[str], side: Path, cfg: dict[str, Any], verbose: bool) -> str:
    """One run of the benchmark against ``side``; its standard output. Exits on failure, showing its tail."""
    env = dict(os.environ)
    keep = typed(cfg, "keep_pythonpath", bool, False, WHERE)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(side), env.get("PYTHONPATH") if keep else None]))
    env["DEVKIT_CHECKOUT"] = str(side)
    threads = typed(cfg, "omp_threads", int, 0, WHERE)
    if threads:
        env["OMP_NUM_THREADS"] = str(threads)
    proc = subprocess.run(
        _expand(argv, side), cwd=ROOT, env=env, capture_output=True, text=True, errors="replace"
    )
    if verbose:
        sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        typer.echo(f"{tail}\nbenchmark failed against {side} (exit {proc.returncode})", err=True)
        raise typer.Exit(proc.returncode)
    return proc.stdout


def _report(samples: dict[str, list[dict[str, float]]]) -> dict[str, dict[str, float | None]]:
    """Per key: best A, best B (ms) and B/A; printed as a table."""
    keys = list(dict.fromkeys(k for side in samples.values() for run in side for k in run))
    rows: dict[str, dict[str, float | None]] = {}
    for k in keys:
        a, b = ([r[k] for r in samples[s] if k in r] for s in ("A", "B"))
        best_a, best_b = (min(v) if v else None for v in (a, b))
        ratio = best_b / best_a if best_a and best_b is not None else None
        rows[k] = {"A": best_a, "B": best_b, "B/A": ratio}
    width = max([len(k) for k in keys] + [3])
    typer.echo(f"{'key':{width}s} {'A ms':>11s} {'B ms':>11s} {'B/A':>7s}")

    def cell(v: float | None, fmt: str) -> str:
        return format(v, fmt) if v is not None else "-".rjust(len(format(0.0, fmt)))

    for k, r in rows.items():
        typer.echo(f"{k:{width}s} {cell(r['A'], '11.4f')} {cell(r['B'], '11.4f')} {cell(r['B/A'], '7.3f')}")
    return rows


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``bench`` command to ``app``, configured by ``[tool.devkit.bench]`` (``cfg``)."""
    try:
        pattern = re.compile(typed(cfg, "pattern", str, PATTERN, WHERE))
    except re.error as exc:
        raise ConfigError(f"[{WHERE}] pattern: {exc}") from exc
    if not {"key", "value"} <= set(pattern.groupindex):
        raise ConfigError(f"[{WHERE}] pattern needs the groups 'key' and 'value'")
    build = [str(a) for a in typed(cfg, "build", list, [], WHERE)]

    def bench(
        a: Annotated[str, typer.Argument(help="Checkout A (the base): a folder or a git ref.")],
        b: Annotated[str, typer.Argument(help="Checkout B (the change): a folder or a git ref.")],
        cmd: Annotated[list[str], typer.Argument(help="The benchmark command, after --.")],
        rounds: Annotated[int, typer.Option(min=1, help="A/B pairs.")] = typed(cfg, "rounds", int, 5, WHERE),
        warmup: Annotated[int, typer.Option(min=0, help="Discarded pairs first.")] = 0,
        out: Annotated[
            Path | None, typer.Option(help="Also write the samples and the summary as JSON.")
        ] = None,
        keep: Annotated[bool, typer.Option(help="Keep temporary worktrees of git refs.")] = False,
        verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show every run's output.")] = False,
    ) -> None:
        """Run CMD against checkouts A and B in turn (A, B, A, B, ...); each key's best time and B/A.

        A and B are folders (already built) or git refs (checked out into a temporary worktree and built
        with [tool.devkit.bench] build). Every run starts in the repository root with PYTHONPATH and
        DEVKIT_CHECKOUT set to its side's folder; {python} and {checkout} in CMD are filled in.

        CMD prints one '<key>: <number> <unit>' line per measurement (unit ns, us, ms or s; lower is
        better), or lines matching [tool.devkit.bench] pattern. Example:
        dev.py bench main HEAD --rounds 7 -- {python} bench.py
        """
        with checkout(a, build, keep) as side_a, checkout(b, build, keep) as side_b:
            sides = {"A": side_a, "B": side_b}
            typer.echo(f"A = {side_a}\nB = {side_b}\n{warmup} warm-up + {rounds} rounds, A then B")
            samples: dict[str, list[dict[str, float]]] = {"A": [], "B": []}
            for i in range(warmup + rounds):
                for name, side in sides.items():
                    found = parse(_run_once(cmd, side, cfg, verbose), pattern)
                    if not found:
                        typer.echo(
                            f"no measurement lines in the output against {side} (pattern {pattern.pattern})",
                            err=True,
                        )
                        raise typer.Exit(1)
                    if i >= warmup:
                        samples[name].append(found)
                typer.echo(f"round {i + 1}/{warmup + rounds}{' (warm-up)' if i < warmup else ''} done")
        summary = _report(samples)
        if out:
            out.write_text(
                json.dumps(
                    {
                        "A": str(side_a),
                        "B": str(side_b),
                        "command": cmd,
                        "samples": samples,
                        "summary": summary,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )

    app.command(
        "bench",
        short_help="Interleaved A/B benchmark of two checkouts: best-of per key, B/A.",
        context_settings={"ignore_unknown_options": True},
    )(bench)
