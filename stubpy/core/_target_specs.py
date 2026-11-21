"""
Resolution of one target spec: a path, a glob or a dotted module name to its targets.
"""
from __future__ import annotations

import glob
import importlib.machinery
import importlib.util
import os
import sys
import sysconfig
from pathlib import Path

from stubpy._constants import SOURCE_SUFFIX, STUB_SUFFIX
from stubpy.analysis import vfs
from stubpy.compiled.detect import is_compiled_module, is_current_abi, is_extension_file, module_stem
from stubpy.core._constants import GLOB_CHARS

from ._exclude import excluded_by
from ._submodules import extension_member
from ._target_models import Target, TargetSpec


def is_module_file(path: Path) -> bool:
    """True for a ``.py`` source, a Cython ``.pyx`` source or an extension module file.

    Parameters
    ----------
    path : pathlib.Path
        The file to classify, by name.

    Returns
    -------
    bool
        Whether stubpy can stub the file.

    Examples
    --------
    >>> from pathlib import Path
    >>> is_module_file(Path("mod.py")), is_module_file(Path("notes.txt"))
    (True, False)
    """
    return path.suffix in (SOURCE_SUFFIX, ".pyx") or is_extension_file(path)


def _resolve(spec: TargetSpec, as_module: bool | None = None) -> list[Target]:
    """Resolve one target spec; ``as_module=None`` auto-detects paths, globs and dotted names."""
    if isinstance(spec, os.PathLike):
        return [_path_target(Path(spec))]
    if not isinstance(spec, str):
        raise TypeError(f"A target must be a str or os.PathLike, not {type(spec).__name__}")
    if as_module:
        return [_module_target(spec)]
    if any(c in spec for c in GLOB_CHARS):
        matches = sorted(glob.glob(spec, recursive=True))
        sources = [Path(m) for m in matches if Path(m).is_dir() or is_module_file(Path(m))]
        if not sources:
            raise FileNotFoundError(f"No Python files or folders match {spec!r}")
        return [_path_target(p) for p in sources]
    path = Path(spec)
    if path.exists():
        return [_path_target(path)]
    if as_module is None and _looks_like_module(spec):
        return [_module_target(spec)]
    raise FileNotFoundError(f"No such file, folder or module: {spec!r}")


def _looks_like_module(spec: str) -> bool:
    return not spec.endswith((SOURCE_SUFFIX, STUB_SUFFIX)) and all(p.isidentifier() for p in spec.split("."))


def _path_target(path: Path) -> Target:
    """Return the :class:`Target` for an existing file or folder."""
    path = path.resolve()
    if not vfs.exists(path):
        raise FileNotFoundError(f"No such file or folder: {path}")
    if vfs.is_dir(path):
        anchor = _import_root(path) if vfs.is_file(path / "__init__.py") else path
        return Target(path, True, anchor)
    if not is_module_file(path):
        raise ValueError(f"{path} is not a Python source (.py), a Cython source (.pyx) or an extension module (.pyd / .so)")
    return Target(path, False, _import_root(path.parent))


def _module_target(name: str) -> Target:
    """Return the :class:`Target` of a module or package named *name*, importable from ``sys.path`` or the working folder."""
    before = set(sys.modules)
    saved_path = list(sys.path)
    if "" not in sys.path and os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())
    try:
        spec = importlib.util.find_spec(name)
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        member = extension_member(name)
        if member is not None:
            return Target(member[0], False, _import_root(member[0].parent), member[1])
        raise ModuleNotFoundError(f"Cannot resolve module {name!r}: {type(exc).__name__}: {exc}") from exc
    finally:
        sys.path[:] = saved_path
        _drop_source_modules(set(sys.modules) - before, name.partition(".")[0])
    if spec is None:
        raise ModuleNotFoundError(f"No module named {name!r}")
    origin = spec.origin
    locations = list(spec.submodule_search_locations or [])
    if not (origin and vfs.is_file(origin)) and not (locations and origin in (None, "namespace")):
        found = _stdlib_file(name, spec)
        if found is not None:
            return _path_target(found.parent if found.name == "__init__.py" else found)
    if origin and origin.endswith(SOURCE_SUFFIX):
        return _path_target(Path(origin).parent if locations else Path(origin))
    if origin and is_extension_file(origin) and Path(origin).is_file():
        return _path_target(Path(origin))
    if locations and (origin is None or origin == "namespace"):
        return _path_target(Path(locations[0]))
    raise ValueError(f"{name} is built into the interpreter and has no source or extension file anywhere ({origin}); "
                     "it cannot be stubbed")


def _drop_source_modules(names: set[str], top: str) -> None:
    """Forget the pure-Python modules of package *top* that resolving a dotted name imported (its parents).

    Other packages it pulled in stay loaded, and so does *top* when an
    extension module of it was loaded: neither can be safely re-imported.
    """
    mine = [n for n in names if n.partition(".")[0] == top]
    if any(is_compiled_module(sys.modules.get(n)) for n in mine):
        return
    for name in mine:
        origin = getattr(sys.modules.get(name), "__file__", None) or ""
        if origin.endswith(SOURCE_SUFFIX):
            sys.modules.pop(name, None)


def _import_root(folder: Path) -> Path:
    """Return the first folder at or above *folder* that is not a package."""
    while vfs.is_file(folder / "__init__.py") and folder.parent != folder:
        folder = folder.parent
    return folder


def _folder_files(folder: Path, exclude: tuple[str, ...], skipped: list[tuple[Path, str]]) -> list[Path]:
    """Return the module files under *folder*, sorted, minus those an *exclude* pattern matches (added to *skipped*).

    One file per module: a ``.py`` source wins over an extension of the same
    name, and an extension this interpreter imports wins over other builds.
    """
    chosen: dict[tuple[Path, str], Path] = {}
    for f in sorted(p for p in vfs.files_under(folder) if is_module_file(p)):
        rel = f.relative_to(folder).as_posix()
        pattern = excluded_by(rel, exclude)
        if pattern is not None:
            skipped.append((f, pattern))
            continue
        key = (f.parent, module_stem(f))
        if key not in chosen or _preference(f) < _preference(chosen[key]):
            chosen[key] = f
    return sorted(chosen.values())


def _preference(path: Path) -> int:
    """Lower is better: source, then an importable extension, then a Cython source, then another build."""
    if path.suffix == SOURCE_SUFFIX:
        return 0
    if path.suffix == ".pyx":
        return 2
    return 1 if is_current_abi(path) else 3


def _stdlib_file(name: str, spec: importlib.machinery.ModuleSpec) -> Path | None:
    """The source of a frozen module (``origin="frozen"``): the frozen loader's file, else the stdlib folder's."""
    candidates: list[Path] = []
    filename = getattr(spec.loader_state, "filename", None)
    if isinstance(filename, str):
        candidates.append(Path(filename))
    module = sys.modules.get(name)
    if isinstance(getattr(module, "__file__", None), str):
        candidates.append(Path(module.__file__))
    for key in ("stdlib", "platstdlib"):
        folder = Path(sysconfig.get_paths().get(key, "")).joinpath(*name.split("."))
        candidates += [folder / "__init__.py", folder.with_name(folder.name + SOURCE_SUFFIX)]
    return next((c for c in candidates if c.suffix == SOURCE_SUFFIX and vfs.is_file(c)), None)
