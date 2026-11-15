"""Inline CSS declarations and small style sheets."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Union

from .._internal._constants import DEFAULT_PRECISION
from .names import PRESENTATION_ATTRIBUTES, svg_name

__all__ = ["Style", "StyleLike", "StyleSheet"]


def _css_name(name: str) -> str:
    return svg_name(name) if "_" in name else name


class Style(MutableMapping[str, object]):
    """Ordered CSS declarations for a ``style`` attribute.

    Keys accept Python spelling (``stroke_width``) or CSS spelling
    (``stroke-width``).

    Examples
    --------
    >>> str(Style(fill="red", stroke_width=2))
    'fill:red;stroke-width:2'
    """

    def __init__(self, declarations: StyleLike | None = None, /, **properties: object) -> None:
        self._data: dict[str, object] = {}
        if isinstance(declarations, str):
            self.update(self.parse(declarations))
        elif declarations is not None:
            self.update(declarations)
        self.update(properties)

    @staticmethod
    def parse(text: str) -> dict[str, str]:
        """Split ``"a:b; c:d"`` into a dict."""
        result: dict[str, str] = {}
        for chunk in text.split(";"):
            name, sep, value = chunk.partition(":")
            if sep and name.strip():
                result[name.strip()] = value.strip()
        return result

    def presentation_only(self) -> Style:
        """Return the subset that are SVG presentation properties."""
        return Style({k: v for k, v in self._data.items() if k in PRESENTATION_ATTRIBUTES})

    def __getitem__(self, key: str) -> object:
        return self._data[_css_name(key)]

    def __setitem__(self, key: str, value: object) -> None:
        if value is None:
            self._data.pop(_css_name(key), None)
        else:
            self._data[_css_name(key)] = value

    def __delitem__(self, key: str) -> None:
        del self._data[_css_name(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Style({self._data!r})"

    def svg_value(self, precision: int = DEFAULT_PRECISION) -> str:
        from .values import format_value

        return ";".join(f"{k}:{format_value(v, precision)}" for k, v in self._data.items())

    def __str__(self) -> str:
        return self.svg_value()


StyleLike = Union[Style, Mapping[str, object], str]


class StyleSheet:
    """Builder for the text of a ``<style>`` element.

    Examples
    --------
    >>> sheet = StyleSheet().rule(".accent", fill="tomato")
    >>> sheet.css()
    '.accent { fill:tomato }'
    """

    def __init__(self, rules: Iterable[tuple[str, StyleLike]] = ()) -> None:
        self._rules: list[tuple[str, Style]] = [(s, Style(d)) for s, d in rules]

    def rule(self, selector: str, declarations: StyleLike | None = None, /, **properties: object) -> StyleSheet:
        self._rules.append((selector, Style(declarations, **properties)))
        return self

    def __iter__(self) -> Iterator[tuple[str, Style]]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def css(self, separator: str = "\n") -> str:
        return separator.join(f"{selector} {{ {style} }}" for selector, style in self._rules)

    def __str__(self) -> str:
        return self.css()
