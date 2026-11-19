"""
CLI commands: config assembly and the ``generate`` / ``check`` / ``render`` runs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stubpy._constants import EXIT_FAILED, EXIT_OK
from stubpy.config import Config, load_config
from stubpy.core.api import check, generate, render
from stubpy.core.results import Report

from ._report import Printer

_OVERRIDES = (
    "imports", "include_private", "include_docstrings", "infer_types", "incremental",
    "resolve_kwargs", "resolve_args", "respect_all", "union_style", "alias_style", "version_branches",
    "verbose", "strict", "target_python",
)


def config_from_args(args: argparse.Namespace) -> Config:
    """Build the run configuration from the command line.

    Loads the nearest config file (unless ``--no-config``) and applies the
    flags given on the command line over it.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line.

    Returns
    -------
    Config
        The effective configuration.

    Examples
    --------
    >>> from stubpy.cli.parser import build_parser
    >>> ns = build_parser().parse_args(["generate", "--no-config", "--strict"])
    >>> config_from_args(ns).strict
    True
    """
    targets = getattr(args, "targets", None) or ([args.target] if getattr(args, "target", None) else [])
    base = Config() if args.no_config else load_config(_search_start(targets))
    changes = {name: getattr(args, name) for name in _OVERRIDES if getattr(args, name, None) is not None}
    if args.exclude:
        changes["exclude"] = tuple(args.exclude)
    if getattr(args, "extend_exclude", None):
        changes["extend_exclude"] = (*base.extend_exclude, *args.extend_exclude)
    if getattr(args, "allow_imports", None):
        current = base.imports if isinstance(base.imports, tuple) else ()
        changes["imports"] = (*current, *args.allow_imports)
    if getattr(args, "deny_imports", None):
        changes["deny_imports"] = (*base.deny_imports, *args.deny_imports)
    return base.replace(**changes)


def _search_start(targets: list[str]) -> Path:
    """Return the folder the config search starts from: the first existing target's, else the working folder."""
    for raw in targets:
        path = Path(raw)
        if path.exists():
            return path if path.is_dir() else path.parent
    return Path.cwd()


def _targets(args: argparse.Namespace) -> list[str] | None:
    """Positional targets plus ``-m`` modules, or ``None`` for the configured ones."""
    return [*args.targets, *args.modules] or None


def run_generate(args: argparse.Namespace, cfg: Config) -> int:
    """Run ``stubpy generate``: write stubs and report them.

    ``--dry-run`` only lists the stubs that would change and ``--diff``
    shows the changes.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line.
    cfg : Config
        The effective configuration.

    Returns
    -------
    int
        ``0`` when every module succeeded, ``1`` when one failed.

    See Also
    --------
    run_check : Report stale stubs without writing.
    """
    out = Printer(args.quiet, cfg.verbose)
    if args.dry_run or args.diff:
        preview = check(_targets(args), args.output, config=cfg)
        if args.dry_run:
            _show_excluded(args, cfg, preview, out)
        changing = set(preview.stale)
        for result in preview:
            if result.output in changing:
                if args.dry_run:
                    out.line(f"would write {out.rel(result.output)}")
                if args.diff:
                    sys.stdout.write(out.diff(result))
        if args.dry_run:
            out.diagnostics(preview)
            out.line(f"{len(changing)} stub(s) would change, {len(preview.failed)} failed.")
            return EXIT_OK if not preview.failed else EXIT_FAILED
    report = generate(_targets(args), args.output, config=cfg)
    _show_excluded(args, cfg, report, out)
    for path in report.written:
        out.line(f"wrote {out.rel(path)}")
    out.diagnostics(report)
    out.line(report.summary())
    return EXIT_OK if report.ok else EXIT_FAILED


def run_check(args: argparse.Namespace, cfg: Config) -> int:
    """Run ``stubpy check``: report stale stubs, with a diff under ``--diff``.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line.
    cfg : Config
        The effective configuration.

    Returns
    -------
    int
        ``0`` when every stub is up to date, ``1`` when one is stale or
        a module failed.

    See Also
    --------
    run_generate : Write the stubs instead.
    """
    report = check(_targets(args), args.output, config=cfg)
    out = Printer(args.quiet, cfg.verbose)
    _show_excluded(args, cfg, report, out)
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
    """Run ``stubpy render``: print one module's stub to stdout.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line; ``args.target`` names the module.
    cfg : Config
        The effective configuration.

    Returns
    -------
    int
        ``0`` on success, ``1`` when the module failed (or warned, with
        ``strict``).

    See Also
    --------
    run_generate : Write the stubs to disk instead.
    """
    result = render(args.target, config=cfg)
    Printer(args.quiet, cfg.verbose).diagnostics(Report(results=[result], strict=cfg.strict))
    if result.ok:
        sys.stdout.write(result.text)
    failed = not result.ok or (cfg.strict and result.warnings)
    return EXIT_FAILED if failed else EXIT_OK


def _show_excluded(args: argparse.Namespace, cfg: Config, report: object, out: Printer) -> None:
    """List the skipped files with ``--show-excluded``, or as one INFO line under ``--verbose``."""
    excluded = getattr(report, "excluded", [])
    if getattr(args, "show_excluded", False):
        for path, pattern in excluded:
            out.line(f"excluded {out.rel(path)} ({pattern})")
    elif cfg.verbose and excluded:
        listed = ", ".join(f"{out.rel(p)} ({pat})" for p, pat in excluded)
        print(f"    [INFO] (targets) excluded {len(excluded)} file(s): {listed}", file=sys.stderr)
