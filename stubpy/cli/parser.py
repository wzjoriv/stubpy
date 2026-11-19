"""
The ``stubpy`` argument parser: ``generate`` (the default), ``check`` and ``render``.
"""
from __future__ import annotations

import argparse

from stubpy.config.options import AliasStyle, UnionStyle, VersionBranches

from .docstrings import add_parser as add_docstrings_parser

COMMANDS = ("generate", "check", "render", "docstrings")

_DESCRIPTION = """\
Generate .pyi stubs, with **kwargs / *args traced to the parameters they forward to.

A TARGET is a .py file, a folder, a quoted glob ("src/**/*.py") or a dotted
module name (mypkg.core).  With no TARGET, the 'targets' and 'modules' of the
nearest stubpy.toml or [tool.stubpy] table are used; CLI flags override the file.
"""

_EPILOG = """\
examples:
  stubpy mod.py                      write mod.pyi next to mod.py
  stubpy src/mypkg -o stubs          write stubs/mypkg/**/*.pyi
  stubpy check src/mypkg -o stubs --diff
  stubpy render mypkg.core --no-import   source analysis only, nothing executed
  stubpy generate -m mypkg._native -o stubs   stub a compiled module by name
  stubpy docstrings sync mypkg/_native.pyi    runtime docstrings into a hand-written stub

exit codes: 0 ok, 1 stale stubs or failed modules, 2 usage error or unknown target
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the ``stubpy`` argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The parser with the ``generate``, ``check``, ``render`` and
        ``docstrings`` sub-commands.

    See Also
    --------
    with_default_command : Insert ``generate`` when no sub-command is given.

    Examples
    --------
    >>> args = build_parser().parse_args(["check", "mod.py", "--diff"])
    >>> args.command, args.targets, args.diff
    ('check', ['mod.py'], True)
    """
    from stubpy import __version__

    shared = _shared_options()
    parser = argparse.ArgumentParser(
        prog="stubpy",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"stubpy {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{generate,check,render,docstrings}")

    gen = sub.add_parser(
        "generate", parents=[shared], help="write stubs (the default command)",
        description="Write .pyi stubs for each TARGET.",
    )
    _add_targets(gen)
    _add_output(gen)
    gen.add_argument("--dry-run", action="store_true", help="write nothing; list the stubs that would change")
    gen.add_argument("--diff", action="store_true", help="print a unified diff for each stub that changes")

    chk = sub.add_parser(
        "check", parents=[shared], help="exit 1 when stubs on disk are stale",
        description="Compare the stubs on disk with what 'generate' would write; nothing is written.",
    )
    _add_targets(chk)
    _add_output(chk)
    chk.add_argument("--diff", action="store_true", help="print a unified diff for each stale stub")

    ren = sub.add_parser(
        "render", parents=[shared], help="print one module's stub to stdout",
        description="Print the stub of one module to stdout; nothing is written.",
    )
    ren.add_argument("target", metavar="TARGET", help="a .py file, an extension module or a dotted module name")
    add_docstrings_parser(sub)
    return parser


def with_default_command(argv: list[str]) -> list[str]:
    """Prefix ``generate`` to the arguments unless a sub-command is given.

    Parameters
    ----------
    argv : list of str
        The command-line arguments without the program name.

    Returns
    -------
    list of str
        *argv* itself when it starts with a sub-command, ``-h``,
        ``--help`` or ``--version``, else *argv* with ``generate`` first.

    Examples
    --------
    >>> with_default_command(["mod.py"])
    ['generate', 'mod.py']
    >>> with_default_command(["check", "mod.py"])
    ['check', 'mod.py']
    """
    if argv and (argv[0] in COMMANDS or argv[0] in ("-h", "--help", "--version")):
        return argv
    return ["generate", *argv]


def _add_targets(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "targets", nargs="*", metavar="TARGET",
        help="files, extension modules, folders, quoted globs or dotted module names "
             "(default: the configured targets)",
    )
    p.add_argument(
        "-m", "--module", dest="modules", action="append", default=[], metavar="MODULE",
        help="an importable module (compiled or not) to stub by dotted name; repeatable",
    )


def _add_output(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-o", "--output", metavar="OUT",
        help="a .pyi file for a single file target, otherwise a stub root folder "
             "(default: output_dir from the config, else next to each source)",
    )


def _flag(p: argparse.ArgumentParser, name: str, field: str, value: object, text: str) -> None:
    p.add_argument(name, dest=field, action="store_const", const=value, default=None, help=text)


def _shared_options() -> argparse.ArgumentParser:
    """Return a parent parser with the options every sub-command takes; each maps onto a Config field."""
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("options")
    g.add_argument("--imports", choices=["all", "none", "stdlib"],
                   help="which modules may be imported: all (default), none (source analysis only) or stdlib")
    _flag(g, "--no-import", "imports", "none", "same as --imports none")
    g.add_argument("--allow-import", dest="allow_imports", metavar="NAME", action="append", default=[],
                   help="also allow importing NAME (pkg or pkg.*) on top of the stdlib; repeatable")
    g.add_argument("--deny-import", dest="deny_imports", metavar="NAME", action="append", default=[],
                   help="never import NAME (pkg or pkg.*); repeatable")
    _flag(g, "--include-private", "include_private", True, "stub names starting with '_'")
    _flag(g, "--include-docstrings", "include_docstrings", True, "use docstrings as stub bodies")
    _flag(g, "--infer-types", "infer_types", True, "fill missing types from NumPy / Google / Sphinx docstrings")
    _flag(g, "--incremental", "incremental", True,
          "merge into existing stubs, keeping edits outside '# stubpy: auto-generated' markers")
    _flag(g, "--no-resolve-kwargs", "resolve_kwargs", False, "keep **kwargs as written")
    _flag(g, "--no-resolve-args", "resolve_args", False, "keep *args as written")
    _flag(g, "--no-respect-all", "respect_all", False, "stub every public name even when __all__ is defined")
    g.add_argument("--union-style", choices=[s.value for s in UnionStyle], help="X | None (modern) or Optional[X]")
    g.add_argument(
        "--alias-style", choices=[s.value for s in AliasStyle],
        help="X: TypeAlias = ... (compatible), type X = ... (pep695), or auto",
    )
    g.add_argument(
        "--version-branches", choices=[s.value for s in VersionBranches],
        help="copy sys.version_info / sys.platform branches into the stub (emit, default) "
             "or keep only this interpreter's branch (resolve)",
    )
    g.add_argument(
        "--exclude", metavar="PATTERN", action="append", default=[],
        help="pattern of files or folders to skip, replacing the defaults (hidden, build output, "
             "<non-identifier>); repeatable",
    )
    g.add_argument("--extend-exclude", dest="extend_exclude", metavar="PATTERN", action="append", default=[],
                   help="pattern to skip on top of the defaults; repeatable")
    g.add_argument("--show-excluded", action="store_true", help="list every skipped file and the pattern that matched")
    g.add_argument(
        "--target-python", metavar="X.Y",
        help="oldest Python the stubs must import on; newer typing names come from typing_extensions (3.10)",
    )
    g.add_argument("--no-config", action="store_true", help="ignore stubpy.toml and [tool.stubpy]")
    _flag(g, "--verbose", "verbose", True, "print every diagnostic, INFO included")
    _flag(g, "--strict", "strict", True, "count warnings as failures")
    g.add_argument("-q", "--quiet", action="store_true", help="print errors only")
    return p
