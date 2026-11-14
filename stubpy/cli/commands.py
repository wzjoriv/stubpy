"""CLI commands: path expansion, config assembly and the file / package / multi-path runs."""
from __future__ import annotations

import argparse
import glob as _glob
import sys
from pathlib import Path

from stubpy.config import EXECUTION_MODES, StubConfig, load_config
from stubpy.core.context import StubContext
from stubpy.core.package import generate_package
from stubpy.core.pipeline import generate_stub

from ._report import print_diagnostics, print_failures


def expand_paths(raw_paths: list[str]) -> list[Path]:
    """Expand glob patterns (``**`` included) and return the deduplicated paths in order."""
    seen: set[str] = set()
    result: list[Path] = []

    for raw in raw_paths:
        if any(c in raw for c in ("*", "?", "[")):
            matches = sorted(_glob.glob(raw, recursive=True))
            if not matches:
                print(f"Warning: glob pattern matched no files: {raw!r}", file=sys.stderr)
            for m in matches:
                if m not in seen:
                    seen.add(m)
                    result.append(Path(m))
        elif raw not in seen:
            seen.add(raw)
            result.append(Path(raw))

    return result


def config_from_args(args: argparse.Namespace) -> StubConfig:
    """Merge the nearest config file with the CLI flags; flags win."""
    first = Path(args.paths[0])
    if args.no_config:
        file_cfg = StubConfig()
    else:
        file_cfg = load_config(first if first.is_dir() else first.parent)

    return StubConfig(
        include_private=args.include_private or file_cfg.include_private,
        include_docstrings=getattr(args, "include_docstrings", False) or file_cfg.include_docstrings,
        verbose=args.verbose or file_cfg.verbose,
        strict=args.strict or file_cfg.strict,
        union_style=getattr(args, "union_style", None) or file_cfg.union_style,
        alias_style=getattr(args, "alias_style", None) or file_cfg.alias_style,
        exclude=list(file_cfg.exclude) + list(getattr(args, "exclude", []) or []),
        output_dir=file_cfg.output_dir,
        execution_mode=EXECUTION_MODES.get(args.execution_mode or "", file_cfg.execution_mode),
        respect_all=False if getattr(args, "no_respect_all", False) else file_cfg.respect_all,
        infer_types_from_docstrings=(
            getattr(args, "infer_types", False) or file_cfg.infer_types_from_docstrings
        ),
        incremental_update=getattr(args, "incremental", False) or file_cfg.incremental_update,
        resolve_kwargs=not getattr(args, "no_resolve_kwargs", False) and file_cfg.resolve_kwargs,
        resolve_args=not getattr(args, "no_resolve_args", False) and file_cfg.resolve_args,
    )


def run_file(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Generate the stub for one ``.py`` file; return the exit code."""
    ctx = StubContext(config=cfg)
    try:
        content = generate_stub(str(target), getattr(args, "output", None), ctx=ctx)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"Error generating stub: {exc}", file=sys.stderr)
        return 1

    out_path = getattr(args, "output", None) or str(target.with_suffix(".pyi"))
    print(f"Stub written to: {out_path}")

    if cfg.verbose and ctx.diagnostics:
        print_diagnostics(ctx)

    if cfg.strict and ctx.diagnostics.has_errors():
        n = len(ctx.diagnostics.errors)
        print(f"\nStub generation completed with {n} error(s). Exiting 1 (--strict).", file=sys.stderr)
        return 1

    if getattr(args, "print", False):
        print("\n--- Generated stub ---\n")
        print(content)

    return 0


def run_package(target: Path, args: argparse.Namespace, cfg: StubConfig) -> int:
    """Generate stubs for every ``.py`` file under a package directory; return the exit code."""
    output_dir = getattr(args, "output", None) or cfg.output_dir
    print(f"Processing package: {target}")
    print(f"Output directory:  {output_dir}" if output_dir else "Output: alongside source files")

    try:
        result = generate_package(
            str(target),
            output_dir=output_dir,
            ctx_factory=lambda: StubContext(config=cfg),
            config=cfg,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"Error processing package: {exc}", file=sys.stderr)
        return 1

    print(f"\n{result.summary()}")

    if result.failed:
        print_failures(result)

    if cfg.strict and result.failed:
        print(
            f"\nPackage processing completed with {len(result.failed)} failed file(s). Exiting 1 (--strict).",
            file=sys.stderr,
        )
        return 1

    return 0


def run_multi(targets: list[Path], args: argparse.Namespace, cfg: StubConfig) -> int:
    """Process several paths, each stub written alongside its source (``-o`` is ignored)."""
    if getattr(args, "output", None):
        print(
            "Warning: -o/--output is ignored when multiple paths are given; "
            "stubs are written alongside each source.",
            file=sys.stderr,
        )

    inner = argparse.Namespace(**{**vars(args), "output": None})

    any_error = False
    for target in targets:
        rc = run_package(target, inner, cfg) if target.is_dir() else run_file(target, inner, cfg)
        if rc != 0:
            any_error = True

    return 1 if any_error else 0
