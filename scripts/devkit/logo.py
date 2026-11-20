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
DEFAULT_PRESETS = ["web"]
IOS_SET = "ios/AppIcon.appiconset"
IOS_ICONS = (  # (point size, scale, idiom)
    (20, 2, "iphone"), (20, 3, "iphone"), (29, 2, "iphone"), (29, 3, "iphone"), (40, 2, "iphone"),
    (40, 3, "iphone"), (60, 2, "iphone"), (60, 3, "iphone"), (20, 1, "ipad"), (20, 2, "ipad"), (29, 1, "ipad"),
    (29, 2, "ipad"), (40, 1, "ipad"), (40, 2, "ipad"), (76, 1, "ipad"), (76, 2, "ipad"), (83.5, 2, "ipad"),
    (1024, 1, "ios-marketing"),
)
ANDROID_DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ANDROID_STORE_SIZE = 512
DESKTOP_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
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


def _ios(doc: Any, export: Any) -> dict[str, bytes]:
    files, images = {}, []
    for points, scale, idiom in IOS_ICONS:
        pixels = round(points * scale)
        name = f"icon-{pixels}.png"
        files[f"{IOS_SET}/{name}"] = doc.export("png", size=pixels, background="white")
        images.append({"filename": name, "idiom": idiom, "scale": f"{scale}x", "size": f"{points:g}x{points:g}"})
    contents = {"images": images, "info": {"author": "devkit", "version": 1}}
    files[f"{IOS_SET}/Contents.json"] = (json.dumps(contents, indent=2) + "\n").encode("utf-8")
    return files


def _android(doc: Any, export: Any) -> dict[str, bytes]:
    files = {f"android/mipmap-{density}/ic_launcher.png": doc.export("png", size=size)
             for density, size in ANDROID_DENSITIES.items()}
    files["android/play-store-icon.png"] = doc.export("png", size=ANDROID_STORE_SIZE)
    return files


def _desktop(doc: Any, export: Any) -> dict[str, bytes]:
    files = {f"desktop/hicolor/{s}x{s}/apps/{STEM}.png": doc.export("png", size=s) for s in DESKTOP_SIZES}
    files[f"desktop/{STEM}.ico"] = export(doc, "ico", sizes=tuple(s for s in DESKTOP_SIZES if s <= ICO_MAX_SIZE))
    files[f"desktop/{STEM}.icns"] = export(doc, "icns")
    files[f"desktop/hicolor/scalable/apps/{STEM}.svg"] = doc.export("svg").encode("utf-8")
    return files


PLATFORMS = {"ios": _ios, "android": _android, "desktop": _desktop}
PRESETS = ("web", *PLATFORMS)


def render_presets(logo: Any, presets: list[str]) -> dict[str, bytes]:
    """Platform icon sets (``ios``, ``android``, ``desktop``) of the default variant, as file name -> bytes."""
    from svgwriter.export import export

    doc = logo()
    files: dict[str, bytes] = {}
    for preset in presets:
        if preset in PLATFORMS:
            files.update(PLATFORMS[preset](doc, export))
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

    presets = typed(cfg, "presets", list, DEFAULT_PRESETS, WHERE)
    if unknown_presets := [p for p in presets if p not in PRESETS]:
        raise ConfigError(f"[{WHERE}] presets: unknown {unknown_presets}; use any of {', '.join(PRESETS)}")
    group = typer.Typer(help="Render the logo assets from the svgwriter source function.", no_args_is_help=True,
                        add_completion=False, context_settings=_HELP)

    @group.command("build")
    def build(
        check: Annotated[bool, typer.Option(
            "--check", help="Write nothing; exit 1 when a file on disk differs from the generated one.")] = False,
        preset: Annotated[list[str] | None, typer.Option(
            "--preset", help=f"Asset set to build, repeatable: {', '.join(PRESETS)}. Defaults to [tool.devkit.logo] presets.")] = None,
    ) -> None:
        """Write the logo assets: web (SVG, PNG, ICO, ICNS, favicon, manifest) and any platform presets."""
        chosen = preset or presets
        if bad := [p for p in chosen if p not in PRESETS]:
            typer.echo(f"unknown preset(s) {bad}; use any of {', '.join(PRESETS)}", err=True)
            raise typer.Exit(2)
        logo = _load(source)
        files = render(logo, variants, png_sizes, formats) if "web" in chosen else {}
        files.update(render_presets(logo, chosen))
        if check:
            stale = [n for n, data in files.items() if not (out / n).is_file() or (out / n).read_bytes() != data]
            for name in stale:
                typer.echo(f"stale: {shown(out / name)}", err=True)
            if stale:
                typer.echo(f"{len(stale)} logo file(s) out of date: run `logo build`", err=True)
                raise typer.Exit(1)
            typer.echo(f"{len(files)} logo file(s) up to date")
            return
        for name, data in files.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(data)
        typer.echo(f"wrote {len(files)} file(s) to {shown(out)}")

    app.add_typer(group, name="logo")
