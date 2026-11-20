"""Every script in ``examples/`` runs cleanly on the current interpreter."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "examples").glob("*.py"))


def test_examples_exist():
    assert len(SCRIPTS) >= 4


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_example_runs(script, tmp_path):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT), os.environ.get("PYTHONPATH", "")]))}
    done = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip()


def test_precommit_example_names_the_hook():
    text = (ROOT / "examples" / "pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "id: stubpy-check" in text
