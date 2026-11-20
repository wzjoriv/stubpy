"""
Submodules that live as attributes of one compiled extension (pybind11 ``def_submodule``), stubbed as a package.
"""
from __future__ import annotations

import sys
import types
from dataclasses import replace
from pathlib import Path

from stubpy._constants import STUB_SUFFIX
from stubpy.compiled.detect import is_extension_file

from .results import StubResult

_INIT = f"__init__{STUB_SUFFIX}"


def attribute_submodules(module: types.ModuleType) -> list[str]:
    """The attribute names of *module* holding its own submodules (``__name__`` is ``<module>.<attribute>``)."""
    name = module.__name__
    return [k for k, v in vars(module).items()
            if isinstance(v, types.ModuleType) and getattr(v, "__name__", None) == f"{name}.{k}"]


def extension_member(name: str) -> tuple[Path, str] | None:
    """The extension file and attribute path of the dotted *name* when it is an attribute submodule, else ``None``."""
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        module = sys.modules.get(".".join(parts[:i]))
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not is_extension_file(file) or not Path(file).is_file():
            continue
        obj = module
        for part in parts[i:]:
            obj = getattr(obj, part, None)
        if isinstance(obj, types.ModuleType) and obj.__name__ == name:
            return Path(file), ".".join(parts[i:])
        return None
    return None


def member_stub(stub: Path, member: str) -> Path:
    """The stub of submodule *member* of the extension whose own stub is *stub*: ``pkg.pyi`` gives ``pkg/fft.pyi``."""
    *folders, last = member.split(".")
    return stub.with_suffix("").joinpath(*folders, last + STUB_SUFFIX)


def package_layout(result: StubResult, member: str, children: list[str]) -> tuple[StubResult, list[tuple[str, Path]]]:
    """Move *result* to ``<module>/__init__.pyi``; return it with the ``(member, stub)`` of each child submodule."""
    out = result.output
    folder = out.parent if out is not None and out.name == _INIT else Path(out or "").with_suffix("")
    moved = replace(result, output=folder / _INIT)
    return moved, [(f"{member}.{c}" if member else c, folder / f"{c}{STUB_SUFFIX}") for c in children]
