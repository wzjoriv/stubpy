"""
Source paths that may point inside a zip archive, such as ``lib.zip/pkg/mod.py``.
Existence, listing and reading helpers that treat real and virtual paths alike.
"""
from __future__ import annotations

import io
import os
import tokenize
import zipfile
from functools import lru_cache
from pathlib import Path

__all__ = ["exists", "files_under", "is_dir", "is_file", "mtime", "read_source"]


def _split(path: Path) -> tuple[Path, str] | None:
    """Return ``(archive, member)`` when *path* lies inside a zip archive, else ``None``."""
    for parent in path.parents:
        if parent.is_file():
            return (parent, path.relative_to(parent).as_posix()) if zipfile.is_zipfile(parent) else None
        if parent.is_dir():
            return None
    return None


@lru_cache(maxsize=32)
def _listing(archive: str, stamp: float) -> tuple[frozenset[str], frozenset[str]]:
    """Return the file and folder members of *archive* (folders without the trailing slash)."""
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
    folders = {"/".join(n.split("/")[:i]) for n in names for i in range(1, n.count("/") + 1)}
    return frozenset(names), frozenset(folders)


def _members(archive: Path) -> tuple[frozenset[str], frozenset[str]]:
    return _listing(str(archive), os.path.getmtime(archive))


def is_file(path: str | os.PathLike[str]) -> bool:
    """Return ``True`` for an existing file, on disk or inside a zip archive.

    Parameters
    ----------
    path : str or os.PathLike
        A real path or a virtual path such as ``lib.zip/pkg/mod.py``.

    Returns
    -------
    bool
        Whether *path* names a file.

    See Also
    --------
    is_dir : The same check for folders.

    Examples
    --------
    >>> is_file(__file__)
    True
    >>> is_file(Path(__file__).parent)
    False
    """
    p = Path(path)
    if p.is_file():
        return True
    split = _split(p)
    return split is not None and split[1] in _members(split[0])[0]


def is_dir(path: str | os.PathLike[str]) -> bool:
    """Return ``True`` for an existing folder, on disk or inside a zip archive.

    Parameters
    ----------
    path : str or os.PathLike
        A real path or a virtual path such as ``lib.zip/pkg``.

    Returns
    -------
    bool
        Whether *path* names a folder.

    See Also
    --------
    is_file : The same check for files.

    Examples
    --------
    >>> is_dir(Path(__file__).parent)
    True
    >>> is_dir(__file__)
    False
    """
    p = Path(path)
    if p.is_dir():
        return True
    split = _split(p)
    return split is not None and split[1] in _members(split[0])[1]


def exists(path: str | os.PathLike[str]) -> bool:
    """Return ``True`` for an existing file or folder, on disk or inside a zip archive.

    Parameters
    ----------
    path : str or os.PathLike
        A real path or a virtual path inside an archive.

    Returns
    -------
    bool
        Whether *path* names a file or a folder.

    Examples
    --------
    >>> exists(__file__), exists(Path(__file__).with_name("no_such_file.py"))
    (True, False)
    """
    return is_file(path) or is_dir(path)


def files_under(folder: str | os.PathLike[str]) -> list[Path]:
    """Return every file below *folder*, recursively, in no particular order.

    Parameters
    ----------
    folder : str or os.PathLike
        A real or virtual folder.

    Returns
    -------
    list of Path
        The files found; empty when *folder* does not exist.

    Examples
    --------
    >>> Path(__file__) in files_under(Path(__file__).parent)
    True
    """
    p = Path(folder)
    if p.is_dir():
        return [f for f in p.rglob("*") if f.is_file()]
    split = _split(p)
    if split is None:
        return []
    archive, inner = split
    return [archive.joinpath(*name.split("/")) for name in _members(archive)[0] if name.startswith(inner + "/")]


def read_source(path: str | os.PathLike[str]) -> str:
    """Return the text of a source file, honouring its encoding cookie and BOM.

    Parameters
    ----------
    path : str or os.PathLike
        A real path or a virtual path inside an archive.

    Returns
    -------
    str
        The decoded source, with ``\\r\\n`` normalised to ``\\n`` for archive members.

    Examples
    --------
    >>> "from __future__" in read_source(__file__)
    True
    """
    p = Path(path)
    split = None if p.is_file() else _split(p)
    if split is None:
        with tokenize.open(p) as fh:
            return fh.read()
    with zipfile.ZipFile(split[0]) as zf:
        data = zf.read(split[1])
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding).replace("\r\n", "\n")


def mtime(path: str | os.PathLike[str]) -> float:
    """Return the modification time of *path*, or of the archive that holds it.

    Parameters
    ----------
    path : str or os.PathLike
        A real path or a virtual path inside an archive.

    Returns
    -------
    float
        Seconds since the epoch.

    Raises
    ------
    FileNotFoundError
        If *path* is neither on disk nor inside an archive.

    Examples
    --------
    >>> mtime(__file__) > 0
    True
    """
    p = Path(path)
    if p.exists():
        return os.path.getmtime(p)
    split = _split(p)
    if split is None:
        raise FileNotFoundError(str(p))
    return os.path.getmtime(split[0])
