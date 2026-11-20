"""``stubpy docstrings`` driven by ``[tool.stubpy.docstrings]``: discovery, ``list``, error reporting, one-line split."""
from __future__ import annotations

import sys
import textwrap

import pytest

from stubpy.cli import main
from stubpy.compiled.docsync import configured_targets
from stubpy.compiled.docsync._discover import runtime_docstring
from stubpy.compiled.docsync._edit import apply_edits, plan_edits
from stubpy.config import Config, DocstringTargets, load_config

from .fakes import fake_module

PYPROJECT = """\
[tool.stubpy.docstrings]
packages = ["src/dspkg"]
import_root = "src"
overrides = {"dspkg.extra" = "stubs/extra.pyi", "dspkg._drop" = ""}
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A src-layout project whose ``.pyx`` modules are importable through a same-stem ``.py``."""
    pkg = tmp_path / "src" / "dspkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name in ("_core", "_drop"):
        (pkg / f"{name}.pyx").write_text("# cython source\n")
        (pkg / f"{name}.py").write_text('def f(x):\n    """Core doc."""\n')
        (pkg / f"{name}.pyi").write_text("def f(x) -> int: ...\n")
    (pkg / "_nostub.pyx").write_text("")
    (pkg / "extra.py").write_text('def g():\n    """Extra doc."""\n')
    (tmp_path / "stubs").mkdir()
    (tmp_path / "stubs" / "extra.pyi").write_text('def g() -> None:\n    """Old."""\n')
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    for name in [m for m in sys.modules if m == "dspkg" or m.startswith("dspkg.")]:
        del sys.modules[name]


def test_config_table_is_loaded_with_paths_resolved(project):
    targets = load_config(project).docstrings
    assert targets.packages == (str(project / "src" / "dspkg"),)
    assert targets.import_root == str(project / "src")
    assert dict(targets.overrides) == {"dspkg.extra": str(project / "stubs" / "extra.pyi"), "dspkg._drop": ""}


def test_unknown_docstrings_key_is_an_error():
    with pytest.raises(ValueError, match="did you mean 'packages'"):
        Config(docstrings={"package": ["x"]})


def test_discovery_applies_overrides(project):
    found = configured_targets(load_config(project).docstrings)
    assert [(t.module, t.stub.relative_to(project).as_posix()) for t in found] == [
        ("dspkg._core", "src/dspkg/_core.pyi"),
        ("dspkg.extra", "stubs/extra.pyi"),
    ]


def test_discovery_rejects_missing_folders_and_stubs(tmp_path):
    with pytest.raises(ValueError, match="not a folder"):
        configured_targets(DocstringTargets(packages=(str(tmp_path / "nope"),)))
    with pytest.raises(ValueError, match="does not exist"):
        configured_targets(DocstringTargets(overrides=(("m", str(tmp_path / "m.pyi")),)))


def test_list_prints_module_and_stub(project, capsys):
    assert main(["docstrings", "list"]) == 0
    out = capsys.readouterr().out
    assert "dspkg._core -> src/dspkg/_core.pyi" in out.replace("\\", "/")
    assert "dspkg.extra -> stubs/extra.pyi" in out.replace("\\", "/")
    assert "2 stub(s)" in out


def test_check_sync_check_with_no_arguments(project):
    assert main(["docstrings", "check"]) == 1
    assert main(["docstrings", "sync"]) == 0
    assert (project / "src" / "dspkg" / "_core.pyi").read_text() == 'def f(x) -> int:\n    """Core doc."""\n'
    assert (project / "stubs" / "extra.pyi").read_text() == 'def g() -> None:\n    """Extra doc."""\n'
    assert main(["docstrings", "check"]) == 0


def test_every_failure_is_reported_then_exit_2(project, capsys):
    (project / "src" / "dspkg" / "_core.py").write_text("raise RuntimeError('not built')\n")
    (project / "stubs" / "extra.pyi").write_text("def g(:\n")
    assert main(["docstrings", "check"]) == 2
    err = capsys.readouterr().err
    assert "dspkg._core" in err and "RuntimeError" in err and "not built" in err
    assert "extra.pyi" in err and "SyntaxError" in err


def test_no_config_and_no_arguments_is_a_usage_error(project):
    assert main(["docstrings", "sync", "--no-config"]) == 2


def test_one_line_definitions_are_split():
    module = fake_module()
    stub = textwrap.dedent("""\
        class Widget: pass
        def lerp(a: float, b: float, t: float = 0.5) -> float: return a
    """)
    edits = plan_edits(stub, lambda path, _node: runtime_docstring(module, path))
    text = apply_edits(stub, edits)
    assert text.startswith('class Widget:\n    """A widget."""\n\ndef lerp')
    assert text.endswith('-> float:\n    """Interpolate."""\n    return a\n')


def test_wrapped_one_line_signature_puts_the_docstring_on_its_own_line():
    module = fake_module()
    stub = textwrap.dedent("""\
        def lerp(
            a: float, b: float, t: float = 0.5
        ) -> float: ...
        class Widget: ...
    """)
    text = apply_edits(stub, plan_edits(stub, lambda path, _node: runtime_docstring(module, path)))
    assert ') -> float:\n    """Interpolate."""\n\nclass Widget:\n    """A widget."""\n' in text
