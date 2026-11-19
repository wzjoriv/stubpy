"""
``stubpy docstrings list|sync|check``: runtime docstrings into hand-written stubs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stubpy._constants import EXIT_FAILED, EXIT_OK, EXIT_USAGE, STUB_SUFFIX
from stubpy.compiled.docsync import (
    Target,
    configured_targets,
    import_module,
    module_name_for,
    sibling_module_file,
    stub_for_module,
    sync_docstrings,
)
from stubpy.config import Config, load_config

from ._report import Printer

_HELP = """\
sync copies the runtime docstrings of a compiled module's functions, classes and
methods into its existing .pyi stub, changing only docstrings; check reports
stubs that are out of date; list prints each module and its stub.  Each STUB is
paired with the module file next to it (pkg/_x.pyi with pkg/_x.pyx or
pkg/_x.*.pyd); a folder means every such stub in it.  -m MODULE names the module
instead; without a STUB its stub is the .pyi next to the module file.  With
neither, the stubs come from [tool.stubpy.docstrings]:

  [tool.stubpy.docstrings]
  packages = ["mypkg"]              # folders searched for *.pyx / extensions with a same-stem .pyi
  import_root = "src"               # module names are relative to it (src layouts)
  overrides = {"mypkg.core" = "stubs/core.pyi", "mypkg._old" = ""}   # "" drops a module

exit codes: 0 up to date, 1 stale stubs (check), 2 usage, import or parse errors
"""


def add_parser(sub: argparse._SubParsersAction) -> None:
    """Register the ``docstrings`` sub-command.

    Parameters
    ----------
    sub : argparse._SubParsersAction
        The top-level sub-command group.

    Examples
    --------
    >>> import argparse
    >>> parser = argparse.ArgumentParser()
    >>> add_parser(parser.add_subparsers(dest="command"))
    >>> parser.parse_args(["docstrings", "list", "-m", "mypkg"]).modules
    ['mypkg']
    """
    p = sub.add_parser(
        "docstrings", help="copy runtime docstrings into hand-written stubs (compiled modules)",
        description=_HELP, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("action", choices=("list", "sync", "check"),
                   help="list prints module and stub; sync writes the stubs; check only reports")
    p.add_argument("stubs", nargs="*", metavar="STUB", help=".pyi files or folders")
    p.add_argument("-m", "--module", dest="modules", action="append", default=[], metavar="MODULE",
                   help="dotted module to read docstrings from; repeatable")
    p.add_argument("--no-config", action="store_true", help="ignore stubpy.toml and [tool.stubpy]")
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


def _paired(stub: Path, module: str | None) -> Target:
    """The target of a STUB argument; the module comes from the file next to it unless named."""
    if module is not None:
        return Target(module, stub, Path.cwd())
    try:
        name, root = module_name_for(stub)
    except ModuleNotFoundError:
        return Target("", stub, None)
    return Target(name, stub, root)


def _jobs(args: argparse.Namespace) -> list[Target | str]:
    """Targets from STUB / ``-m`` arguments, else from the config; a ``str`` is a module whose stub is next to it."""
    stubs = _stub_files(args.stubs)
    if stubs and len(args.modules) > 1:
        raise ValueError("give one -m MODULE with STUB arguments, or several -m without")
    if stubs:
        return [_paired(s, args.modules[0] if args.modules else None) for s in stubs]
    if args.modules:
        return list(args.modules)
    cfg = Config() if args.no_config else load_config(Path.cwd())
    if not cfg.docstrings:
        raise ValueError("give at least one STUB or -m MODULE, or configure [tool.stubpy.docstrings]")
    return list(configured_targets(cfg.docstrings))


def _load(job: Target | str) -> tuple[Path | None, object]:
    """Import the module of *job*; return ``(stub, module)``, or ``(stub, message)`` when that fails."""
    stub = job.stub if isinstance(job, Target) else None
    name = job.module if isinstance(job, Target) else job
    if not name:
        return stub, f"no module file next to {stub}"
    try:
        module = import_module(name, job.root if isinstance(job, Target) else Path.cwd())
        return (stub or stub_for_module(module)), module
    except Exception as exc:
        return stub, f"cannot import {name} ({type(exc).__name__}: {exc}); build the extensions first"


def run_docstrings(args: argparse.Namespace) -> int:
    """Run ``stubpy docstrings``: list, sync or check stub docstrings.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line; ``args.action`` is ``list``, ``sync`` or
        ``check``.

    Returns
    -------
    int
        ``0`` when everything is up to date or was synced, ``1`` when
        ``check`` found stale stubs, ``2`` for a usage, import or parse
        error.

    See Also
    --------
    stubpy.compiled.docsync.sync_docstrings : The sync of one stub.
    """
    out = Printer(args.quiet, False)
    try:
        jobs = _jobs(args)
    except (ValueError, ImportError) as exc:
        print(f"stubpy: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.action == "list":
        for job in jobs:
            module, stub = (job.module, out.rel(job.stub)) if isinstance(job, Target) else (job, "?")
            out.line(f"{module} -> {stub}")
        out.line(f"{len(jobs)} stub(s)")
        return EXIT_OK
    write = args.action == "sync"
    stale: list[str] = []
    errors: list[str] = []
    for job in jobs:
        stub, module = _load(job)
        if isinstance(module, str):
            errors.append(f"{out.rel(stub)}: {module}" if stub else module)
            continue
        try:
            result = sync_docstrings(stub, module, write=write)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{out.rel(stub)}: {type(exc).__name__}: {exc}")
            continue
        if result.changed:
            stale.append(str(stub))
            out.line(f"{'updated' if write else 'stale'} {out.rel(stub)}: {', '.join(result.updated)}")
    for message in errors:
        print(f"stubpy: error: {message}", file=sys.stderr)
    out.line(f"{len(jobs)} stub(s) checked, {len(stale)} {'updated' if write else 'out of date'}, "
             f"{len(errors)} error(s).")
    if errors:
        return EXIT_USAGE
    return EXIT_FAILED if stale and not write else EXIT_OK
