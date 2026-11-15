"""``stubpy docstrings sync|check``: runtime docstrings into hand-written stubs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stubpy._constants import EXIT_FAILED, EXIT_OK, EXIT_USAGE, STUB_SUFFIX
from stubpy.compiled.docsync import import_module, sibling_module_file, stub_for_module, sync_docstrings

from ._report import Printer

_HELP = """\
sync copies the runtime docstrings of a compiled module's functions, classes and
methods into its existing .pyi stub, changing only docstrings; check reports
stubs that are out of date.  Each STUB is paired with the module file next to it
(pkg/_x.pyi with pkg/_x.pyx or pkg/_x.*.pyd); a folder means every such stub in
it.  -m MODULE names the module instead; without a STUB its stub is the .pyi next
to the module file.

exit codes: 0 up to date, 1 stale stubs (check), 2 usage or import error
"""


def add_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``docstrings`` on the top-level sub-command parser."""
    p = sub.add_parser(
        "docstrings", help="copy runtime docstrings into hand-written stubs (compiled modules)",
        description=_HELP, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("action", choices=("sync", "check"), help="sync writes the stubs; check only reports")
    p.add_argument("stubs", nargs="*", metavar="STUB", help=".pyi files or folders")
    p.add_argument("-m", "--module", dest="modules", action="append", default=[], metavar="MODULE",
                   help="dotted module to read docstrings from; repeatable")
    p.add_argument("-q", "--quiet", action="store_true", help="print errors only")


def _stub_files(raw: list[str]) -> list[Path]:
    out: list[Path] = []
    for item in raw:
        path = Path(item)
        if path.is_dir():
            out.extend(p for p in sorted(path.rglob(f"*{STUB_SUFFIX}")) if sibling_module_file(p) is not None)
        else:
            out.append(path)
    return out


def _jobs(args: argparse.Namespace) -> list[tuple[Path, str | None]]:
    """``(stub, module)`` pairs; *module* ``None`` means the module next to the stub."""
    stubs = _stub_files(args.stubs)
    if stubs and len(args.modules) > 1:
        raise ValueError("give one -m MODULE with STUB arguments, or several -m without")
    if stubs:
        return [(s, args.modules[0] if args.modules else None) for s in stubs]
    if not args.modules:
        raise ValueError("give at least one STUB or -m MODULE")
    return [(stub_for_module(import_module(name, Path.cwd())), name) for name in args.modules]


def run_docstrings(args: argparse.Namespace) -> int:
    """Sync or check docstrings; return the exit code."""
    out = Printer(args.quiet, False)
    try:
        jobs = _jobs(args)
    except ImportError as exc:
        print(f"stubpy: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    write = args.action == "sync"
    stale = errors = 0
    for stub, module in jobs:
        try:
            result = sync_docstrings(stub, module, write=write)
        except (ImportError, OSError, SyntaxError) as exc:
            print(f"stubpy: error: {out.rel(stub)}: {type(exc).__name__}: {exc}", file=sys.stderr)
            errors += 1
            continue
        if not result.changed:
            continue
        stale += 1
        verb = "updated" if write else "stale"
        out.line(f"{verb} {out.rel(stub)}: {', '.join(result.updated)}")
    out.line(f"{len(jobs)} stub(s) checked, {stale} {'updated' if write else 'out of date'}, {errors} error(s).")
    if errors:
        return EXIT_USAGE
    return EXIT_FAILED if stale and not write else EXIT_OK
