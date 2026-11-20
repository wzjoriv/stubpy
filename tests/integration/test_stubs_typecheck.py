"""
The stubs generated for the test corpora type-check under mypy, apart from a short list of known source-level errors.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config

pytestmark = pytest.mark.skipif(importlib.util.find_spec("mypy") is None, reason="mypy is not installed")

CORPORA = Path(__file__).resolve().parents[2] / "corpora"
RASTER = CORPORA / "svgraster" / "svgraster"
OLDEST = "3.10"
ERROR = re.compile(r"^(?P<path>.+?):\d+: error: .*\[(?P<code>[\w-]+)\]$")

_COMPOSE = "the mixin's receiver is annotated with a subclass, exactly as in the source"
_INPLACE = "the in-place operator returns a narrower type than the operator it overrides, exactly as in the source"
KNOWN = {
    ("misc", "svgwriter/elements/_compose.pyi"): _COMPOSE,
    ("misc", "svgwriter/elements/container.pyi"): _INPLACE,
    ("override", "svgwriter/elements/container.pyi"): _INPLACE,
    ("misc", "svgwriter/elements/shapes/_path.pyi"): _INPLACE,
    ("override", "svgwriter/elements/shapes/_path.pyi"): _INPLACE,
    ("overload-overlap", "svgwriter/elements/shapes/_path.pyi"): "the source's overloads of __add__ overlap",
    ("misc", "svgwriter/transform.pyi"): _INPLACE,
    ("override", "svgraster/raster/rasterizer.pyi"): "the subclass widens the compiled base's fill(rule) from int to str, as in the source",
}


def _built(stem: str) -> bool:
    return any((RASTER / f"{stem}{s}").is_file() for s in importlib.machinery.EXTENSION_SUFFIXES)


def _errors(root: Path, version: str | None) -> set[tuple[str, str]]:
    """Run mypy over the stubs in *root*; return the ``(code, file)`` of each error."""
    args = [sys.executable, "-m", "mypy", ".", "--ignore-missing-imports", "--no-error-summary",
            "--cache-dir", str(root.parent / "mypy-cache")]
    if version:
        args += ["--python-version", version]
    run = subprocess.run(args, cwd=root, capture_output=True, text=True, check=False)
    assert run.returncode in (0, 1), run.stderr + run.stdout
    found = (ERROR.match(line) for line in run.stdout.splitlines())
    return {(m["code"], m["path"].replace("\\", "/")) for m in found if m}


@pytest.fixture(scope="module")
def stubs(tmp_path_factory) -> dict[str, Path]:
    """Generate each corpus once: svgwriter with and without importing it, and svgraster where it is built."""
    roots = {}
    for name, config in (("svgwriter", Config()), ("svgwriter-source", Config(imports="none"))):
        roots[name] = tmp_path_factory.mktemp(name)
        stubpy.generate(str(CORPORA / "svgwriter"), str(roots[name]), config=config)
    if _built("_scanline"):
        roots["svgraster"] = tmp_path_factory.mktemp("svgraster")
        stubpy.generate(RASTER, roots["svgraster"])
    return roots


@pytest.mark.parametrize("version", [None, OLDEST], ids=["current", OLDEST])
@pytest.mark.parametrize("corpus", ["svgwriter", "svgwriter-source", "svgraster"])
def test_corpus_stubs_type_check(stubs, corpus, version):
    if corpus not in stubs:
        pytest.skip("svgraster is not built for this interpreter")
    new = _errors(stubs[corpus], version) - KNOWN.keys()
    assert not new, sorted(new)
