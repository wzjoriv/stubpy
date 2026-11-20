"""The import policy: ``imports`` / ``deny_imports`` decide what stubpy may execute; blocked targets use the source."""
from __future__ import annotations

import importlib.machinery
import shutil
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config
from stubpy.analysis._guard import ImportBlockedError, PolicyFinder, import_guard
from stubpy.cli import main
from stubpy.config import ImportPolicy
from tests.conftest import write_tree


@pytest.fixture
def project(tmp_path):
    """``polpkg`` (imports ``poldep`` and ``json``) beside ``poldep``, which records that it ran."""
    root = write_tree(tmp_path / "src", {
        "polpkg/__init__.py": "",
        "polpkg/core.py": "import json\nimport poldep\n\ndef run(x: int = poldep.N) -> int: ...\n",
        "polpkg/plain.py": "import json\n\ndef dump(x: int) -> str: ...\n",
        "poldep/__init__.py": "import builtins\nbuiltins.POLDEP_RAN = True\nN = 3\n",
    })
    yield root
    for name in [m for m in sys.modules if m.split(".")[0] in ("polpkg", "poldep")]:
        sys.modules.pop(name, None)
    import builtins
    builtins.__dict__.pop("POLDEP_RAN", None)


def _render(root: Path, rel: str, **cfg):
    return stubpy.render(root / rel, config=Config(**cfg))


@pytest.mark.parametrize("name, allowed", [
    ("json", [True, False, True, True, True]),
    ("json.decoder", [True, False, True, True, True]),
    ("polpkg", [True, False, False, True, False]),
    ("polpkg.core", [True, False, False, True, False]),
    ("poldep", [True, False, False, False, False]),
])
def test_policy_allows(name, allowed):
    policies = [ImportPolicy("all"), ImportPolicy("none"), ImportPolicy("stdlib"), ImportPolicy(("polpkg",)),
                ImportPolicy(("polpkg",), ("polpkg.*",))]
    assert [p.allows(name) for p in policies] == allowed


def test_parents_of_an_allowed_module_are_allowed():
    policy = ImportPolicy(("pkg.sub.leaf",))
    assert policy.allows("pkg") and policy.allows("pkg.sub") and policy.allows("pkg.sub.leaf.x")
    assert not policy.allows("pkg.other")


def test_all_imports_everything(project):
    result = _render(project, "polpkg/core.py")
    assert result.ok and "def run(x: int = poldep.N) -> int" in result.text
    assert not any("blocked" in d.message for d in result.diagnostics)
    import builtins
    assert builtins.POLDEP_RAN is True


def test_none_executes_nothing(project):
    result = _render(project, "polpkg/core.py", imports="none")
    import builtins
    assert result.ok and not hasattr(builtins, "POLDEP_RAN")
    assert any("execution skipped" in d.message for d in result.diagnostics)


def test_indirect_import_is_blocked_and_the_target_uses_its_source(project):
    result = _render(project, "polpkg/core.py", imports=["polpkg"])
    import builtins
    assert result.ok and not hasattr(builtins, "POLDEP_RAN")
    note = next(d for d in result.diagnostics if "blocked by stubpy import policy" in d.message)
    assert note.level.name == "INFO" and "poldep" in note.message
    assert "def run(x: int = poldep.N) -> int: ..." in result.text


def test_allowed_target_with_stdlib_imports_is_imported(project):
    result = _render(project, "polpkg/plain.py", imports=["polpkg"])
    assert not any("blocked" in d.message for d in result.diagnostics)
    assert any("Symbol table" in d.message for d in result.diagnostics)


def test_stdlib_blocks_the_project_itself(project):
    result = _render(project, "polpkg/plain.py", imports="stdlib")
    assert any("blocked by stubpy import policy: polpkg" in d.message for d in result.diagnostics)


def test_deny_overrides_allow(project):
    result = _render(project, "polpkg/core.py", deny_imports=["poldep"])
    import builtins
    assert not hasattr(builtins, "POLDEP_RAN")
    assert any("blocked by stubpy import policy: poldep" in d.message for d in result.diagnostics)


def test_sys_modules_and_meta_path_are_restored(project):
    before_modules, before_finders = set(sys.modules), list(sys.meta_path)
    _render(project, "polpkg/core.py", imports=["polpkg"])
    assert set(sys.modules) - before_modules == set()
    assert sys.meta_path == before_finders


def test_guard_is_removed_on_errors():
    before = list(sys.meta_path)
    with pytest.raises(RuntimeError), import_guard(ImportPolicy("stdlib")) as guard:
        assert isinstance(sys.meta_path[0], PolicyFinder) and guard is sys.meta_path[0]
        raise RuntimeError("boom")
    assert sys.meta_path == before


def test_guard_blocks_and_leaves_loaded_modules_alone():
    with import_guard(ImportPolicy("none")) as guard:
        import json  # noqa: F401  # already loaded: not affected
        with pytest.raises(ImportBlockedError, match="blocked by stubpy import policy: stubpy_never_there"):
            __import__("stubpy_never_there")
    assert guard.blocked == ["stubpy_never_there"]


def test_unrestricted_policy_installs_nothing():
    with import_guard(ImportPolicy("all")) as guard:
        assert guard is None


RASTER = Path(__file__).resolve().parents[2] / "corpora" / "svgraster" / "svgraster"
BUILT = next((RASTER / f"_scanline{s}" for s in importlib.machinery.EXTENSION_SUFFIXES
              if (RASTER / f"_scanline{s}").is_file()), None)


@pytest.mark.skipif(BUILT is None, reason="svgraster is not built for this interpreter")
@pytest.mark.parametrize("imports, ok", [("stdlib", False), (["_scanline"], True)])
def test_extension_modules_follow_the_policy(tmp_path, imports, ok):
    copy = tmp_path / BUILT.name
    shutil.copy(BUILT, copy)
    result = stubpy.render(copy, config=Config(imports=imports))
    assert result.ok is ok
    if not ok:
        assert "blocked by stubpy import policy: _scanline" in result.errors[0].message


def test_cli_flags(project, capsys):
    target = str(project / "polpkg" / "core.py")
    assert main(["render", target, "--no-config", "--allow-import", "polpkg", "--verbose"]) == 0
    assert "blocked by stubpy import policy: poldep" in capsys.readouterr().err
    assert main(["render", target, "--no-config", "--deny-import", "poldep", "--verbose"]) == 0
    assert "blocked by stubpy import policy: poldep" in capsys.readouterr().err
    assert main(["render", target, "--no-config", "--imports", "none", "--verbose"]) == 0
    assert "execution skipped" in capsys.readouterr().err
