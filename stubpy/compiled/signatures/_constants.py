"""
Named constants of signature text handling.
"""
from __future__ import annotations

ANY_ARRAY = "numpy.typing.NDArray[typing.Any]"

#: nanobind ``ndarray[...]`` entries kept as ``Annotated`` metadata, in nanobind's order
ARRAY_METADATA_KEYS: tuple[str, ...] = ("shape", "order", "device")
