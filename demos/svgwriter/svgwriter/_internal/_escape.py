"""XML escaping for text and attribute values."""

from __future__ import annotations

__all__ = ["escape_attribute", "escape_text"]

_TEXT_TABLE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;"})
_ATTRIBUTE_TABLE = str.maketrans(
    {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "\n": "&#10;",
        "\r": "&#13;",
        "\t": "&#9;",
    }
)


def escape_text(text: str) -> str:
    """Escape character data."""
    return text.translate(_TEXT_TABLE)


def escape_attribute(text: str) -> str:
    """Escape a value for use inside double quotes."""
    return text.translate(_ATTRIBUTE_TABLE)
