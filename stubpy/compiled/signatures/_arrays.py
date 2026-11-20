"""
nanobind ``ndarray[...]`` signature text as a NumPy annotation, optionally keeping shape, order and device.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ._constants import ANY_ARRAY, ARRAY_METADATA_KEYS

__all__ = ["array_metadata", "nanobind_array", "NB_NDARRAY"]

NB_NDARRAY = re.compile(r"\b(?:numpy\.)?ndarray\[([^\[\]]*=[^\[\]]*)\]")
_DTYPE = re.compile(r"\bdtype\s*=\s*([A-Za-z_]\w*)")
_KEEP = ContextVar("stubpy_array_metadata", default=False)


@contextmanager
def array_metadata(enabled: bool = True) -> Iterator[None]:
    """Keep ``shape``, ``order`` and ``device`` of nanobind arrays while signatures are read.

    Parameters
    ----------
    enabled : bool, optional
        Whether arrays become ``Annotated[NDArray[...], dict(...)]``.
        Defaults to ``True``.

    See Also
    --------
    nanobind_array : The conversion this switches.

    Examples
    --------
    >>> with array_metadata():
    ...     nanobind_array("dtype=float32, shape=(*, 3)")
    'typing.Annotated[numpy.typing.NDArray[numpy.float32], dict(shape=(None, 3))]'
    """
    token = _KEEP.set(enabled)
    try:
        yield
    finally:
        _KEEP.reset(token)


def nanobind_array(text: str) -> str:
    """The annotation for the inside of a nanobind ``ndarray[...]``.

    Parameters
    ----------
    text : str
        The ``key=value`` list, e.g. ``dtype=float32, shape=(*, 3), order='C'``.

    Returns
    -------
    str
        ``numpy.typing.NDArray[numpy.<dtype>]``; inside an :func:`array_metadata`
        block, wrapped in ``typing.Annotated`` with the ``shape``, ``order`` and
        ``device`` the text gives (``*`` dimensions become ``None``).

    See Also
    --------
    array_metadata : Switch the metadata on.

    Examples
    --------
    >>> nanobind_array("dtype=float32, shape=(*, 3)")
    'numpy.typing.NDArray[numpy.float32]'
    """
    dtype = _DTYPE.search(text)
    base = f"numpy.typing.NDArray[numpy.{dtype.group(1)}]" if dtype else ANY_ARRAY
    meta = _metadata(text) if _KEEP.get() else ""
    return f"typing.Annotated[{base}, dict({meta})]" if meta else base


def _split(text: str) -> list[str]:
    """*text* split on top-level commas, outside brackets and quotes."""
    out, depth, quote, start = [], 0, "", 0
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return [s.strip() for s in out if s.strip()]


def _metadata(text: str) -> str:
    """The ``key=value`` text of the shape, order and device entries present in *text*."""
    found = {}
    for part in _split(text):
        key, _, value = part.partition("=")
        if key.strip() in ARRAY_METADATA_KEYS:
            found[key.strip()] = value.strip()
    return ", ".join(
        f"{key}={_shape(found[key]) if key == 'shape' else _literal(found[key])}"
        for key in ARRAY_METADATA_KEYS if key in found
    )


def _shape(value: str) -> str:
    """A dimension tuple (``(None, 3)``) from nanobind's ``(*, 3)``."""
    return repr(tuple(int(d) if d.isdigit() else None for d in _split(value.strip("()"))))


def _literal(value: str) -> str:
    """*value* as a quoted string literal."""
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        parsed = value
    return repr(parsed if isinstance(parsed, str) else value)
