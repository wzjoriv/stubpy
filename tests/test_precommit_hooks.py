"""The pre-commit hook definitions at the repository root."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from stubpy.cli.parser import build_parser, with_default_command

HOOKS = Path(__file__).resolve().parents[1] / ".pre-commit-hooks.yaml"


def _hooks() -> dict[str, str]:
    text = HOOKS.read_text(encoding="utf-8")
    ids = re.findall(r"^- id: (\S+)$", text, re.M)
    entries = re.findall(r"^  entry: (.+)$", text, re.M)
    return dict(zip(ids, entries, strict=True))


def test_hook_ids():
    assert set(_hooks()) == {"stubpy-check", "stubpy-generate"}


@pytest.mark.parametrize("hook, command", [("stubpy-check", "check"), ("stubpy-generate", "generate")])
def test_entries_parse(hook, command):
    program, *args = _hooks()[hook].split()
    assert program == "stubpy"
    parsed = build_parser().parse_args(with_default_command(args))
    assert parsed.command == command
