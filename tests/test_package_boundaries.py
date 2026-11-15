"""Import boundaries inside stubpy: private-module ownership and package layering."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1] / "stubpy"

FORBIDDEN = {
    "stubpy.analysis": ("stubpy.emit", "stubpy.core.pipeline", "stubpy.core.api", "stubpy.cli"),
    "stubpy.compiled": ("stubpy.emit", "stubpy.core.pipeline", "stubpy.core.api", "stubpy.cli"),
    "stubpy.resolve": ("stubpy.emit", "stubpy.core.pipeline", "stubpy.core.api", "stubpy.cli"),
    "stubpy.emit": ("stubpy.core.pipeline", "stubpy.core.api", "stubpy.cli"),
}


def _modules() -> dict[str, tuple[Path, bool]]:
    """Map each dotted module name to ``(path, is_package)``."""
    out = {}
    for path in sorted(PKG_ROOT.rglob("*.py")):
        rel = path.relative_to(PKG_ROOT.parent).with_suffix("")
        parts = list(rel.parts)
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        out[".".join(parts)] = (path, is_pkg)
    return out


MODULES = _modules()


def _package_of(module: str) -> str:
    """Return the package a module lives in (a package's ``__init__`` lives in itself)."""
    return module if MODULES[module][1] else module.rpartition(".")[0]


def _within(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _is_private(segment: str) -> bool:
    return segment.startswith("_") and not segment.startswith("__")


def _imports(module: str) -> list[tuple[str, list[str], int]]:
    """Return ``(target_module, imported_names, lineno)`` for every import in *module*."""
    path, _ = MODULES[module]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _package_of(module)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, [], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            found.append((target, [a.name for a in node.names], node.lineno))
    return [(t, names, ln) for t, names, ln in found if _within(t, "stubpy")]


def _targets(target: str, names: list[str]) -> list[str]:
    """Expand ``from target import name`` to the submodules it actually imports."""
    out = [target]
    out += [f"{target}.{n}" for n in names if f"{target}.{n}" in MODULES]
    return out


@pytest.mark.parametrize("module", sorted(MODULES))
def test_private_modules_are_only_imported_by_their_owner(module):
    importer_pkg = _package_of(module)
    for target, names, lineno in _imports(module):
        for full in _targets(target, names):
            parts = full.split(".")
            for i, segment in enumerate(parts):
                if _is_private(segment):
                    owner = ".".join(parts[:i])
                    assert _within(importer_pkg, owner), (
                        f"{module}:{lineno} imports {full}, which is private to {owner}"
                    )


@pytest.mark.parametrize("module", sorted(MODULES))
def test_private_names_are_not_imported_across_packages(module):
    importer_pkg = _package_of(module)
    for target, names, lineno in _imports(module):
        if target not in MODULES:
            continue
        owner = _package_of(target)
        for name in names:
            if _is_private(name) and f"{target}.{name}" not in MODULES:
                assert _within(importer_pkg, owner), (
                    f"{module}:{lineno} imports private name {name} from {target}"
                )


@pytest.mark.parametrize("module", sorted(MODULES))
def test_layering(module):
    for layer, forbidden in FORBIDDEN.items():
        if not _within(module, layer):
            continue
        for target, names, lineno in _imports(module):
            for full in _targets(target, names):
                for bad in forbidden:
                    assert not _within(full, bad), f"{module}:{lineno} imports {full} (layer {layer})"


def test_module_inventory_is_not_empty():
    assert "stubpy._constants" in MODULES
    assert any(m.startswith("stubpy.emit.") for m in MODULES)
