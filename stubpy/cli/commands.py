"""CLI commands: config assembly and the ``generate`` / ``check`` / ``render`` runs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stubpy._constants import EXIT_FAILED, EXIT_OK
from stubpy.config import Config, load_config
from stubpy.core.api import check, generate, render

from ._report import Printer

_OVERRIDES = (
    "mode", "include_private", "include_docstrings", "infer_types", "incremental",
    "resolve_kwargs", "resolve_args", "respect_all", "union_style", "alias_style", "verbose", "strict",
)


def config_from_args(args: argparse.Namespace) -> Config:
    """Load the nearest config file (unless ``--no-config``) and apply the flags given on the command line."""
    targets = getattr(args, "targets", None) or ([args.target] if getattr(args, "target", None) else [])
    base = Config() if args.no_config else load_config(_search_start(targets))
    changes = {name: getattr(args, name) for name in _OVERRIDES if getattr(args, name, None) is not None}
    if args.exclude:
        changes["exclude"] = (*base.exclude, *args.exclude)
    return base.replace(**changes)


def _search_start(targets: list[str]) -> Path:
    """Return the folder the config search starts from: the first existing target's, else the working folder."""
    for raw in targets:
        path = Path(raw)
        if path.exists():
            return path if path.is_dir() else path.parent
    return Path.cwd()


def run_generate(args: argparse.Namespace, cfg: Config) -> int:
    """Write stubs and report them; return the exit code."""
    report = generate(args.targets or None, args.output, config=cfg)
    out = Printer(args.quiet, cfg.verbose)
    for path in report.written:
        out.line(f"wrote {out.rel(path)}")
    out.diagnostics(report)
    out.line(report.summary())
    return EXIT_OK if report.ok else EXIT_FAILED


def run_check(args: argparse.Namespace, cfg: Config) -> int:
    """Report stale stubs (with a diff under ``--diff``); return the exit code."""
    report = check(args.targets or None, args.output, config=cfg)
    out = Printer(args.quiet, cfg.verbose)
    stale = set(report.stale)
    for result in report:
        if result.output in stale:
            out.line(f"stale {out.rel(result.output)}")
            if args.diff:
                sys.stdout.write(out.diff(result))
    out.diagnostics(report)
    out.line(report.summary())
    return EXIT_OK if report.ok else EXIT_FAILED


def run_render(args: argparse.Namespace, cfg: Config) -> int:
    """Print one module's stub to stdout; return the exit code."""
    result = render(args.target, config=cfg)
    Printer(args.quiet, cfg.verbose).result_diagnostics(result, force=not result.ok)
    if result.ok:
        sys.stdout.write(result.text)
    failed = not result.ok or (cfg.strict and result.warnings)
    return EXIT_FAILED if failed else EXIT_OK
