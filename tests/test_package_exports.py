"""The public surface of the stubpy package."""
from __future__ import annotations

import importlib

import pytest

import stubpy


@pytest.mark.parametrize("name", stubpy.__all__)
def test_all_names_are_importable(name):
    assert hasattr(stubpy, name)
    namespace: dict = {}
    exec(f"from stubpy import {name}", namespace)
    assert namespace[name] is getattr(stubpy, name)


def test_all_has_no_duplicates():
    assert len(stubpy.__all__) == len(set(stubpy.__all__))


def test_metadata():
    assert isinstance(stubpy.__version__, str) and stubpy.__version__
    assert stubpy.__author__ == "Josue N Rivera"


def test_cli_help_exits_cleanly(capsys):
    from stubpy.cli import main

    try:
        rc = main(["--help"])
    except SystemExit as exc:
        rc = exc.code
    assert rc in (0, None)
    assert "usage: stubpy" in capsys.readouterr().out


def test_dunder_main_uses_cli_main():
    from stubpy.cli import main

    module = importlib.import_module("stubpy.__main__")
    assert module.main is main
