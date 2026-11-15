"""svgraster's developer commands: conformance-suite download, in-place builds and benchmarks.

    python scripts/dev.py svgraster fetch-suite        # download the W3C SVG 1.1 SE test suite (git-ignored)
    python scripts/dev.py svgraster build              # build the native layers in place, single-threaded
    python scripts/dev.py svgraster conformance        # score svgraster against the suite's reference PNGs
    python scripts/dev.py svgraster bench              # time the built-in scenes, native against numpy
    python scripts/dev.py svgraster gen-unicode        # regenerate the shaping tables, fetch BidiCharacterTest.txt
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


#: Unicode Character Database files the shaping tables are generated from
UCD_FILES = ("Scripts.txt", "ArabicShaping.txt", "IndicSyllabicCategory.txt", "IndicPositionalCategory.txt",
             "BidiBrackets.txt", "BidiMirroring.txt")
#: The official bidi conformance test, kept with the git-ignored suite
BIDI_TEST = "BidiCharacterTest.txt"
UCD_URL = "https://www.unicode.org/Public/{version}/ucd/{name}"
#: The generated table module
UCD_MODULE = PROJECT / "svgraster" / "shaping" / "_ucd.py"
UNICODE_DIR = SUITE / "unicode"
INDIC_RANGES = ((0x0900, 0x0DFF), (0xA8E0, 0xA8FF), (0x200C, 0x200D), (0x25CC, 0x25CC), (0x00A0, 0x00A0))
ROW_ITEMS = 6


def _ucd_rows(text: str):
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            yield [f.strip() for f in line.split(";")]


def _span(field: str) -> tuple[int, int]:
    lo, _, hi = field.partition("..")
    return int(lo, 16), int(hi or lo, 16)


def _in_indic(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in INDIC_RANGES)


def _merge(ranges: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for lo, hi, value in sorted(ranges):
        if out and out[-1][2] == value and out[-1][1] + 1 == lo:
            out[-1] = (out[-1][0], hi, value)
        else:
            out.append((lo, hi, value))
    return out


def _indic(text: str) -> dict[int, str]:
    out = {}
    for fields in _ucd_rows(text):
        lo, hi = _span(fields[0])
        for cp in range(lo, hi + 1):
            if _in_indic(cp):
                out[cp] = fields[1]
    return out


def _emit(name: str, items: list[str], opener: str, closer: str) -> list[str]:
    lines = [f"{name} = {opener}"]
    for i in range(0, len(items), ROW_ITEMS):
        lines.append("    " + " ".join(items[i:i + ROW_ITEMS]))
    lines.append(closer)
    return lines


def _ucd_module(files: dict[str, str], version: str) -> str:
    scripts = _merge([(*_span(f[0]), f[1]) for f in _ucd_rows(files["Scripts.txt"])])
    joining = {int(f[0], 16): f[2] for f in _ucd_rows(files["ArabicShaping.txt"]) if f[2] != "U"}
    syllabic = _indic(files["IndicSyllabicCategory.txt"])
    positional = _indic(files["IndicPositionalCategory.txt"])
    brackets = {int(f[0], 16): (int(f[1], 16), f[2]) for f in _ucd_rows(files["BidiBrackets.txt"])}
    mirror = {int(f[0], 16): int(f[1], 16) for f in _ucd_rows(files["BidiMirroring.txt"])}
    out = [f'"""Unicode {version} tables generated by ``scripts/dev.py svgraster gen-unicode``; do not edit."""',
           "", f"UNICODE_VERSION = {version!r}"]
    out += _emit("SCRIPT_RANGES", [f"(0x{a:X}, 0x{b:X}, {s!r})," for a, b, s in scripts], "(", ")")
    out += _emit("JOINING_TYPES", [f"0x{k:X}: {v!r}," for k, v in sorted(joining.items())], "{", "}")
    out += _emit("INDIC_SYLLABIC", [f"0x{k:X}: {v!r}," for k, v in sorted(syllabic.items())], "{", "}")
    out += _emit("INDIC_POSITIONAL", [f"0x{k:X}: {v!r}," for k, v in sorted(positional.items())], "{", "}")
    out += _emit("BRACKETS", [f"0x{k:X}: (0x{p:X}, {t!r})," for k, (p, t) in sorted(brackets.items())], "{", "}")
    out += _emit("MIRRORS", [f"0x{k:X}: 0x{v:X}," for k, v in sorted(mirror.items())], "{", "}")
    return "\n".join(out) + "\n"


def _fetch_text(version: str, name: str) -> str:
    with urllib.request.urlopen(UCD_URL.format(version=version, name=name), timeout=120) as response:
        return response.read().decode("utf-8")


@app.command("gen-unicode")
def gen_unicode(
    version: str = typer.Option("", help="Unicode version (default: the interpreter's unicodedata version)."),
    test: bool = typer.Option(True, "--test/--no-test", help=f"Also download {BIDI_TEST}."),
) -> None:
    """Generate svgraster/shaping/_ucd.py from the Unicode Character Database."""
    import unicodedata

    version = version or unicodedata.unidata_version
    files = {name: _fetch_text(version, name) for name in UCD_FILES}
    UCD_MODULE.write_text(_ucd_module(files, version), encoding="utf-8", newline="\n")
    typer.echo(f"wrote {UCD_MODULE.relative_to(ROOT)} (Unicode {version})")
    if test:
        UNICODE_DIR.mkdir(parents=True, exist_ok=True)
        (UNICODE_DIR / BIDI_TEST).write_text(_fetch_text(version, BIDI_TEST), encoding="utf-8", newline="\n")
        typer.echo(f"wrote {(UNICODE_DIR / BIDI_TEST).relative_to(ROOT)}")
