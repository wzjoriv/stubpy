"""svgraster's developer commands: conformance-suite download, in-place builds and benchmarks.

    python scripts/dev.py svgraster fetch-suite        # download the W3C SVG 1.1 SE test suite (git-ignored)
    python scripts/dev.py svgraster build              # build the native layers in place, single-threaded
    python scripts/dev.py svgraster conformance        # score svgraster against the suite's reference PNGs
    python scripts/dev.py svgraster bench              # time the built-in scenes, native against numpy
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import typer

__all__ = ["app"]

#: The repository root (``scripts/demo_tools/svgraster.py`` is two folders below it)
ROOT = Path(__file__).resolve().parents[2]
#: The svgraster project folder
PROJECT = ROOT / "demos" / "svgraster"
#: Where the conformance suite is unpacked (git-ignored)
SUITE = PROJECT / "conformance" / "suite"
#: The W3C SVG 1.1 Second Edition test suite archive
SUITE_URL = "https://www.w3.org/Graphics/SVG/Test/20110816/archives/W3C_SVG_11_TestSuite.tar.gz"
#: Archive folders the tests and their references need
SUITE_FOLDERS = ("svg", "png", "images", "resources")
CHUNK = 1 << 16

app = typer.Typer(
    name="svgraster",
    help=__doc__.split("\n\n")[0],
    no_args_is_help=True,
    add_completion=False,
)


def _download(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as fh:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while chunk := response.read(CHUNK):
            fh.write(chunk)
            done += len(chunk)
        if total and done != total:
            raise typer.BadParameter(f"incomplete download: {done} of {total} bytes")


def _safe_members(archive: tarfile.TarFile):
    for member in archive.getmembers():
        parts = Path(member.name).parts
        if not parts or parts[0] not in SUITE_FOLDERS:
            continue
        if member.issym() or member.islnk() or ".." in parts or Path(member.name).is_absolute():
            continue
        yield member


@app.command("fetch-suite")
def fetch_suite(
    url: str = typer.Option(SUITE_URL, help="Archive URL."),
    force: bool = typer.Option(False, "--force", help="Download again even when the suite is present."),
) -> None:
    """Download and unpack the W3C SVG 1.1 test suite into demos/svgraster/conformance/suite."""
    if (SUITE / "svg").is_dir() and not force:
        typer.echo(f"suite already present: {SUITE.relative_to(ROOT)} (use --force to refresh)")
        return
    SUITE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "suite.tar.gz"
        typer.echo(f"downloading {url}")
        _download(url, archive_path)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = list(_safe_members(archive))
            archive.extractall(SUITE, members=members)
    count = len(list((SUITE / "svg").glob("*.svg")))
    typer.echo(f"unpacked {count} tests into {SUITE.relative_to(ROOT)}")


@app.command("build")
def build(
    clean: bool = typer.Option(False, "--clean", help="Remove the build folder first."),
) -> None:
    """Build svgraster's native layers in place (single-threaded)."""
    if clean:
        shutil.rmtree(PROJECT / "build", ignore_errors=True)
    code = subprocess.call([sys.executable, "setup.py", "build_ext", "--inplace", "-j", "1"], cwd=PROJECT)
    raise typer.Exit(code)


@app.command("conformance")
def conformance(
    pattern: str = typer.Option("", "--filter", help="Only tests whose name contains this text."),
    report: Path = typer.Option(PROJECT / "conformance" / "report.md", help="Markdown report path."),
) -> None:
    """Run ``python -m svgraster conformance`` on the downloaded suite."""
    if not (SUITE / "svg").is_dir():
        typer.echo("suite missing; run: python scripts/dev.py svgraster fetch-suite", err=True)
        raise typer.Exit(2)
    args = [sys.executable, "-m", "svgraster", "conformance", "--suite", str(SUITE), "--report", str(report)]
    if pattern:
        args += ["--filter", pattern]
    raise typer.Exit(subprocess.call(args, cwd=PROJECT))


@app.command("bench")
def bench(
    size: int = typer.Option(512, help="Output width in pixels."),
    threads: int = typer.Option(0, help="OpenMP threads (0 = default)."),
) -> None:
    """Time the built-in scenes with the native layers and the numpy fallbacks."""
    args = [sys.executable, "-m", "svgraster", "bench", "--compare", "--size", str(size)]
    if threads:
        args += ["--threads", str(threads)]
    raise typer.Exit(subprocess.call(args, cwd=PROJECT))
