"""
The stub / module pairs ``[tool.stubpy.docstrings]`` describes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stubpy._constants import STUB_SUFFIX
from stubpy.analysis.loader import find_import_target
from stubpy.config import DocstringTargets

from ..detect import is_extension_file, module_stem


@dataclass(frozen=True)
class Target:
    """A hand-written stub and the module its docstrings come from; *root* goes first on ``sys.path``."""
    module: str
    stub: Path
    root: Path | None = None


def configured_targets(options: DocstringTargets) -> list[Target]:
    """Return the targets of *options*, sorted by module.

    Every ``*.pyx`` or extension module under ``options.packages`` with a
    same-stem ``.pyi`` next to it, then ``options.overrides`` applied.

    Raises
    ------
    ValueError
        If a package is not a folder, an override stub does not exist, or a
        module lies outside ``import_root``.
    """
    root = Path(options.import_root).resolve() if options.import_root else None
    found: dict[str, Target] = {}
    for package in options.packages:
        folder = Path(package)
        if not folder.is_dir():
            raise ValueError(f"docstrings.packages: {package!r} is not a folder")
        for source in sorted(folder.rglob("*")):
            if source.suffix != ".pyx" and not is_extension_file(source):
                continue
            stub = source.with_name(module_stem(source) + STUB_SUFFIX)
            if stub.is_file():
                name, where = _module_name(source, root)
                found.setdefault(name, Target(name, stub, where))
    for module, stub in options.overrides:
        if not stub:
            found.pop(module, None)
            continue
        if not Path(stub).is_file():
            raise ValueError(f"docstrings.overrides: stub {stub!r} of {module!r} does not exist")
        found[module] = Target(module, Path(stub), root)
    return [found[m] for m in sorted(found)]


def _module_name(source: Path, root: Path | None) -> tuple[str, Path | None]:
    """The dotted name of the module *source* defines and the folder it imports from."""
    if root is not None:
        try:
            rel = source.resolve().with_name(module_stem(source)).relative_to(root)
        except ValueError as exc:
            raise ValueError(f"docstrings: {source} is outside import_root {root}") from exc
        return ".".join(rel.parts), root
    target = find_import_target(source)
    if target is not None:
        return target.name, target.root
    return module_stem(source), source.parent
