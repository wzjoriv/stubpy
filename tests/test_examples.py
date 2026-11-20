"""Every script in ``examples/`` runs cleanly on the current interpreter."""
from __future__ import annotations

import contextlib
import io
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "examples").glob("*.py"))
NO_PROCESSES = sys.platform in ("emscripten", "wasi")


def _run_in_process(script: Path, cwd: Path) -> str:
    """Run *script* in this interpreter (for platforms without subprocesses) and return its output."""
    out = io.StringIO()
    previous = Path.cwd()
    os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(out):
            runpy.run_path(str(script), run_name="__main__")
    finally:
        os.chdir(previous)
    return out.getvalue()


def test_examples_exist():
    assert len(SCRIPTS) >= 4


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_example_runs(script, tmp_path):
    if NO_PROCESSES:
        assert _run_in_process(script, tmp_path).strip()
        return
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH", "")]))}
    done = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip()


def test_in_process_runner(tmp_path):
    assert _run_in_process(SCRIPTS[0], tmp_path).strip()


def test_precommit_example_names_the_hook():
    text = (ROOT / "examples" / "pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "id: stubpy-check" in text
