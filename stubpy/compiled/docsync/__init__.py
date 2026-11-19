"""Copy runtime docstrings into hand-written ``.pyi`` stubs, changing nothing but the docstrings."""
from __future__ import annotations

import os
import types
from dataclasses import dataclass
from pathlib import Path

from ._discover import import_module, module_name_for, runtime_docstring, sibling_module_file, stub_for_module
from ._edit import apply_edits, plan_edits
from ._targets import Target, configured_targets

__all__ = [
    "DocSync", "Target", "configured_targets", "import_module", "module_name_for", "sibling_module_file",
    "stub_for_module", "sync_docstrings",
]


@dataclass(frozen=True)
class DocSync:
    """The outcome of syncing one stub.

    Attributes
    ----------
    path : Path
        The stub file.
    module : str
        The module its docstrings came from.
    text : str
        The stub text with the runtime docstrings (equal to the file when up to date).
    updated : tuple of str
        Qualified names of the definitions whose docstring changed.
    written : bool
        ``True`` when the file was rewritten.
    """
    path: Path
    module: str
    text: str
    updated: tuple[str, ...]
    written: bool = False

    @property
    def changed(self) -> bool:
        """``True`` when the stub on disk is out of date."""
        return bool(self.updated)


def sync_docstrings(
    stub_path: str | os.PathLike[str],
    module: str | types.ModuleType | None = None,
    *,
    write: bool = True,
) -> DocSync:
    """Copy the runtime docstrings of a module into its existing ``.pyi`` stub.

    Top-level functions, classes and their methods and properties get the
    docstring of the matching runtime object, with binding signature lines
    (pybind11, Cython ``embedsignature``, C API text signatures) removed.
    Only docstrings change: a body of ``...`` becomes the docstring, an
    existing docstring is replaced, a one-line definition is split so the
    docstring opens its body, and every other byte of the file (line
    endings, comments, formatting, ``@overload`` variants) is kept.

    Parameters
    ----------
    stub_path : str or os.PathLike
        The hand-written stub.
    module : str, module or None
        The module to read docstrings from, as a dotted name or a module
        object.  ``None`` imports the module whose file sits next to the
        stub with the same stem (``pkg/_x.pyx`` or ``pkg/_x.*.pyd`` for
        ``pkg/_x.pyi``).
    write : bool
        Rewrite the stub when it changes; ``False`` only reports.

    Returns
    -------
    DocSync
        The new text and the names whose docstrings changed.

    Raises
    ------
    FileNotFoundError
        If the stub does not exist.
    ImportError
        If the module cannot be found or imported.

    Examples
    --------
    >>> import stubpy
    >>> result = stubpy.sync_docstrings("pkg/_native.pyi")  # doctest: +SKIP
    >>> result.updated  # doctest: +SKIP
    ('scale', 'Vec.norm')
    """
    path = Path(stub_path)
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    live = _module(path, module)
    edits = plan_edits(text, lambda qualified, _node: runtime_docstring(live, qualified))
    new_text = apply_edits(text, edits)
    written = False
    if write and new_text != text:
        path.write_bytes(new_text.encode("utf-8"))
        written = True
    return DocSync(path, live.__name__, new_text, tuple(e.name for e in edits), written)


def _module(stub: Path, module: str | types.ModuleType | None) -> types.ModuleType:
    if isinstance(module, types.ModuleType):
        return module
    if isinstance(module, str):
        return import_module(module, Path.cwd())
    name, root = module_name_for(stub)
    return import_module(name, root)
