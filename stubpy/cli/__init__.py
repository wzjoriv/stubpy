"""The ``stubpy`` command-line interface.

Configuration is read from the nearest ``stubpy.toml`` or ``[tool.stubpy]``
section above the first path; CLI flags override it.
"""
from __future__ import annotations

import sys

from .commands import config_from_args, expand_paths, run_file, run_multi, run_package
from .parser import build_parser

__all__ = ["build_parser", "main"]


def main(argv: list[str] | None = None) -> int:
    """Run the ``stubpy`` command.

    Parameters
    ----------
    argv : list[str], optional
        Arguments to parse; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        ``0`` on success; ``1`` on error, or with ``--strict`` when any
        ERROR diagnostic was recorded.
    """
    args = build_parser().parse_args(argv)

    targets = expand_paths(args.paths)
    if not targets:
        print("Error: no files matched the given path(s) or pattern(s).", file=sys.stderr)
        return 1

    cfg = config_from_args(args)

    if len(targets) == 1:
        t = targets[0]
        return run_package(t, args, cfg) if t.is_dir() else run_file(t, args, cfg)
    return run_multi(targets, args, cfg)
