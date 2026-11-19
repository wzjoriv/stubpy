"""Load an extension module whose parent packages fail to import, under empty placeholder parents."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

from ._importing import ImportTarget


def extension_alone(path: Path, target: ImportTarget, failure: BaseException) -> Any:
    """Load extension *path* as *target* with placeholders standing in for its parents; raise *failure* if it fails.

    The placeholders are removed again; the extension stays loaded (it cannot be re-imported).
    """
    parts = target.name.split(".")
    placeholders: list[str] = []
    for i in range(1, len(parts)):
        name = ".".join(parts[:i])
        if name in sys.modules:
            continue
        package = types.ModuleType(name)
        package.__path__ = [str(Path(target.root).joinpath(*parts[:i]))]
        package.__package__ = name
        sys.modules[name] = package
        placeholders.append(name)
    try:
        spec = importlib.util.spec_from_file_location(target.name, path)
        if spec is None or spec.loader is None:
            raise failure
        module = importlib.util.module_from_spec(spec)
        sys.modules[target.name] = module
        try:
            spec.loader.exec_module(module)
        except (Exception, SystemExit) as exc:
            sys.modules.pop(target.name, None)
            raise failure from exc
        return module
    finally:
        for name in placeholders:
            sys.modules.pop(name, None)
