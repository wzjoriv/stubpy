"""JPEG Huffman tables with an extra constructor."""
from __future__ import annotations

from .. import _codec


class HuffmanTable(_codec.HuffmanTable):
    """A Huffman table that can also build itself with one code length for every symbol."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def uniform(cls, symbols: int, **kwargs) -> HuffmanTable:
        """Every symbol with the same code length."""
        length = max(1, (symbols - 1).bit_length())
        counts = [0] * 16
        counts[length - 1] = symbols
        return cls(counts, list(range(symbols)), **kwargs)
