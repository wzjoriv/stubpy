"""
Logo tool: render every logo asset (SVG, PNGs, ICO, ICNS, favicon, web manifest) from one svgwriter function.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import ConfigError, root_path, typed
from .paths import ROOT, shown

__all__ = ["render", "register"]

WHERE = "tool.devkit.logo"
REQUIRES: tuple[str, ...] = ("svgwriter",)
EXTERNAL: tuple[str, ...] = ()
MISSING = "pip install svgwriter (add it to your dev extra)"

DEFAULT_VARIANT = "default"
DEFAULT_OUTPUT = "docs/_static/logo"
DEFAULT_PNG_SIZES = [16, 32, 48, 64, 128, 256, 512]
FORMATS = ("svg", "png", "ico", "icns", "favicon", "webmanifest")
STEM = "logo"
FAVICON_SIZES = (16, 32, 48)
APPLE_TOUCH_SIZE = 180
MANIFEST_SIZES = (192, 512)
ICO_MAX_SIZE = 256
MANIFEST_NAME = "site.webmanifest"
_HELP = {"help_option_names": ["-h", "--help"]}


def _load(source: str) -> Any:
    """The function named by ``source`` (``"package.module:function"``), imported from the project root."""
    module_name, sep, attr = source.partition(":")
    if not sep or not module_name or not attr:
        raise ConfigError(f"[{WHERE}] source: {source!r} is not 'module:function'")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        func = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise ConfigError(f"[{WHERE}] source: cannot load {source!r} from {ROOT}: {exc}") from exc
    if not callable(func):
        raise ConfigError(f"[{WHERE}] source: {source!r} is not callable")
    return func


def _stem(variant: str) -> str:
    return STEM if variant == DEFAULT_VARIANT else f"{STEM}-{variant}"


def render(logo: Any, variants: dict[str, dict[str, Any]], png_sizes: list[int],
           formats: tuple[str, ...] = FORMATS) -> dict[str, bytes]:
    """Every asset of the logo as file name -> bytes, without writing anything.

    Parameters
    ----------
    logo : callable
        ``logo(**variant)`` returning an ``svgwriter.Document``.
    variants : dict
        Variant name -> keyword arguments of ``logo``; ``"default"`` is always rendered.
    png_sizes : list of int
        Square PNG sizes (``logo-<size>.png``).
    formats : tuple of str
        Any of ``svg``, ``png``, ``ico``, ``icns``, ``favicon``, ``webmanifest``. The manifest needs the
        192 and 512 px PNGs; they are added to the PNG sizes of the default variant when missing.

    Returns
    -------
    dict
        File name (relative to the output folder) -> content. Only the default variant has the favicon
        files and the manifest.
    """
    try:
        import svgwriter
        from svgwriter.export import export
    except ImportError as exc:
        typer.echo(MISSING, err=True)
        raise typer.Exit(2) from exc

    files: dict[str, bytes] = {}
    for variant, kwargs in {DEFAULT_VARIANT: {}, **variants}.items():
        doc = logo(**kwargs)
        if not isinstance(doc, svgwriter.Document):
            raise ConfigError(f"[{WHERE}] source returned {type(doc).__name__} for variant {variant!r}, "
                              "not an svgwriter Document")
        stem = _stem(variant)
        main = variant == DEFAULT_VARIANT
        sizes = set(png_sizes) if "png" in formats else set()
        if main and "webmanifest" in formats:
            sizes.update(MANIFEST_SIZES)
        if "svg" in formats:
            files[f"{stem}.svg"] = doc.export("svg").encode("utf-8")
        for size in sorted(sizes):
            files[f"{stem}-{size}.png"] = doc.export("png", size=size)
        if "ico" in formats:
            ico_sizes = tuple(sorted(s for s in png_sizes if s <= ICO_MAX_SIZE))
            files[f"{stem}.ico"] = export(doc, "ico", **({"sizes": ico_sizes} if ico_sizes else {}))
        if "icns" in formats:
            files[f"{stem}.icns"] = export(doc, "icns")
        if main and "favicon" in formats:
            files["favicon.ico"] = export(doc, "ico", sizes=FAVICON_SIZES)
            files["apple-touch-icon.png"] = doc.export("png", size=APPLE_TOUCH_SIZE)
        if main and "webmanifest" in formats:
            icons = [{"src": f"{stem}-{s}.png", "sizes": f"{s}x{s}", "type": "image/png"} for s in MANIFEST_SIZES]
            files[MANIFEST_NAME] = (json.dumps({"icons": icons}, indent=2) + "\n").encode("utf-8")
    return files


def register(app: typer.Typer, cfg: dict[str, Any]) -> None:
    """Add the ``logo`` command group, configured by ``[tool.devkit.logo]`` (``cfg``)."""
    if "source" not in cfg:
        raise ConfigError(f"[{WHERE}] needs source ('package.module:function' returning an svgwriter Document)")
    source = typed(cfg, "source", str, "", WHERE)
    variants = typed(cfg, "variants", dict, {}, WHERE)
    for name, kwargs in variants.items():
        if not isinstance(kwargs, dict):
            raise ConfigError(f"[{WHERE}] variants.{name} must be a table of keyword arguments")
        if name == DEFAULT_VARIANT:
            raise ConfigError(f"[{WHERE}] variants: {DEFAULT_VARIANT!r} always exists; name the variant otherwise")
    out = Path(root_path(typed(cfg, "output", str, DEFAULT_OUTPUT, WHERE)))
    png_sizes = typed(cfg, "png_sizes", list, DEFAULT_PNG_SIZES, WHERE)
    if not all(isinstance(s, int) and not isinstance(s, bool) and s > 0 for s in png_sizes):
        raise ConfigError(f"[{WHERE}] png_sizes must be a list of positive integers")
    formats = tuple(typed(cfg, "formats", list, list(FORMATS), WHERE))
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ConfigError(f"[{WHERE}] formats: unknown {unknown}; use any of {', '.join(FORMATS)}")

    group = typer.Typer(help="Render the logo assets from the svgwriter source function.", no_args_is_help=True,
                        add_completion=False, context_settings=_HELP)

    @group.command("build")
    def build(
        check: Annotated[bool, typer.Option(
            "--check", help="Write nothing; exit 1 when a file on disk differs from the generated one.")] = False,
    ) -> None:
        """Write every asset of every variant (SVG, PNG, ICO, ICNS, favicon, web manifest)."""
        files = render(_load(source), variants, png_sizes, formats)
        if check:
            stale = [n for n, data in files.items() if not (out / n).is_file() or (out / n).read_bytes() != data]
            for name in stale:
                typer.echo(f"stale: {shown(out / name)}", err=True)
            if stale:
                typer.echo(f"{len(stale)} logo file(s) out of date: run `logo build`", err=True)
                raise typer.Exit(1)
            typer.echo(f"{len(files)} logo file(s) up to date")
            return
        out.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (out / name).write_bytes(data)
        typer.echo(f"wrote {len(files)} file(s) to {shown(out)}")

    app.add_typer(group, name="logo")
