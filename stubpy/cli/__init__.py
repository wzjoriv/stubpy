"""
The ``stubpy`` command-line interface: ``generate``, ``check``, ``render`` and ``docstrings``.
"""
from __future__ import annotations

import sys

from stubpy._constants import EXIT_USAGE

from .commands import config_from_args, run_check, run_generate, run_render
from .docstrings import run_docstrings
from .parser import build_parser, with_default_command

__all__ = ["build_parser", "main"]

_RUNNERS = {"generate": run_generate, "check": run_check, "render": run_render}


def main(argv: list[str] | None = None) -> int:
    """Run the ``stubpy`` command.

    Parameters
    ----------
    argv : list of str, optional
        Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        ``0`` when everything is fine; ``1`` when stubs are stale or a
        module failed (warnings too, with ``--strict``); ``2`` for a usage
        error, an invalid config file or a target that cannot be found.

    See Also
    --------
    build_parser : The parser behind the command.

    Examples
    --------
    >>> main(["--version"])  # doctest: +SKIP
    """
    args = build_parser().parse_args(with_default_command(sys.argv[1:] if argv is None else list(argv)))
    if args.command == "docstrings":
        try:
            return run_docstrings(args)
        except (OSError, ValueError) as exc:
            print(f"stubpy: error: {exc}", file=sys.stderr)
            return EXIT_USAGE
    try:
        cfg = config_from_args(args)
        return _RUNNERS[args.command](args, cfg)
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(f"stubpy: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
