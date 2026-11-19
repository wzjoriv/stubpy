"""
Python-visible declarations of Cython sources (``.pyx``), read without compiling them.
"""
from __future__ import annotations

from pathlib import Path

from stubpy.analysis import vfs

from ._cython import available, read_with_cython
from ._reader import read_pyx
from .models import PyxClass, PyxEnum, PyxFunction, PyxModule, PyxParam

__all__ = [
    "PyxClass", "PyxEnum", "PyxFunction", "PyxModule", "PyxParam", "merge_signature", "pyx_attribute_types", "pyx_signatures",
    "read_pyx", "read_pyx_file", "synthetic_module",
]


def read_pyx_file(path: str | Path) -> PyxModule:
    """Read a ``.pyx`` file into a :class:`PyxModule`.

    Uses Cython's parser when Cython is installed, else the built-in
    reader; a source Cython cannot parse falls back to the built-in reader.

    Parameters
    ----------
    path : str or pathlib.Path
        The ``.pyx`` file.

    Returns
    -------
    PyxModule
        The declarations Python can see, with enum defaults qualified.

    Raises
    ------
    OSError
        If the file cannot be read.

    See Also
    --------
    read_pyx : The same from source text, without Cython.
    """
    text = vfs.read_source(path)
    if available():
        try:
            return read_with_cython(text, Path(path).stem).qualify_enum_defaults()
        except Exception:
            pass
    return read_pyx(text).qualify_enum_defaults()


from ._synth import merge_signature, pyx_attribute_types, pyx_signatures, synthetic_module  # noqa: E402
