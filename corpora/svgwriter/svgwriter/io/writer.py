"""Serialization of element trees to SVG text."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import InitVar, dataclass, field
from typing import Any, TypedDict
from xml.sax.saxutils import escape, quoteattr

from .._internal._typing import AnyPath, NotRequired, Required
from ..attributes.protocols import TextSink
from ..attributes.values import DEFAULT_PRECISION, format_value
from ..elements.base import Element

__all__ = ["SerializeOptions", "SerializeSettings", "Writer", "iter_chunks", "to_string", "write"]

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class SerializeSettings(TypedDict, total=False):
    """The keyword arguments :class:`SerializeOptions` accepts."""

    indent: Required[str]
    precision: int
    xml_declaration: bool
    encoding: NotRequired[str]


def _default_namespaces() -> dict[str, str]:
    return {"xmlns": SVG_NS, "xmlns:xlink": XLINK_NS}


@dataclass(kw_only=True)
class SerializeOptions:
    """Output settings.

    Parameters
    ----------
    pretty : bool
        Indent and break lines; ``False`` writes everything on one line.
    indent : str
        One level of indentation when pretty.
    precision : int
        Maximum decimals for numbers.
    xml_declaration : bool
        Emit ``<?xml ...?>``.
    """

    pretty: InitVar[bool] = True
    indent: str = "  "
    precision: int = DEFAULT_PRECISION
    xml_declaration: bool = True
    encoding: str = "utf-8"
    namespaces: dict[str, str] = field(default_factory=_default_namespaces)
    newline: str = field(init=False, default="\n")

    def __post_init__(self, pretty: bool) -> None:
        if not pretty:
            self.indent = ""
            self.newline = ""


class Writer:
    """Turns an element tree into text, honoring :class:`SerializeOptions`."""

    def __init__(self, options: SerializeOptions | None = None, **kwargs: Any) -> None:
        self.options = options if options is not None else SerializeOptions(**kwargs)

    def _open_tag(self, element: Element, extra: dict[str, str]) -> str:
        attributes = {**extra, **{k: format_value(v, self.options.precision) for k, v in element.attributes.items()}}
        return "<" + " ".join([element.tag] + [f"{k}={quoteattr(v)}" for k, v in attributes.items()])

    def _element(self, element: Element, depth: int, extra: dict[str, str]) -> Iterator[str]:
        opts = self.options
        pad = opts.indent * depth
        yield pad + self._open_tag(element, extra)
        if not element.children:
            yield "/>"
            return
        yield ">"
        for child in element.children:
            if isinstance(child, str):
                yield escape(child)
                continue
            yield opts.newline
            yield from self._element(child, depth + 1, {})
        yield opts.newline + pad + f"</{element.tag}>"

    def iter_chunks(self, element: Element, *, xml_declaration: bool | None = None) -> Iterator[str]:
        """Yield the document in pieces (useful for streaming)."""
        opts = self.options
        if opts.xml_declaration if xml_declaration is None else xml_declaration:
            yield f'<?xml version="1.0" encoding="{opts.encoding}" standalone="no"?>\n'
        namespaces = dict(opts.namespaces) if element.tag == "svg" else {}
        yield from self._element(element, 0, namespaces)
        yield opts.newline

    def to_string(self, element: Element, **kwargs: Any) -> str:
        return "".join(self.iter_chunks(element, **kwargs))

    def write(self, element: Element, target: AnyPath | TextSink) -> None:
        """Write to a filesystem path or any object with ``write(str)``."""
        if isinstance(target, (str, os.PathLike)):
            with open(target, "w", encoding=self.options.encoding, newline="\n") as handle:
                handle.write(self.to_string(element))
        elif isinstance(target, TextSink):
            target.write(self.to_string(element))
        else:
            raise TypeError(f"cannot write to {type(target).__name__}")


def iter_chunks(element: Element, **kwargs: Any) -> Iterator[str]:
    """Module-level shortcut for :meth:`Writer.iter_chunks`."""
    xml_declaration = kwargs.pop("xml_declaration", None)
    return Writer(**kwargs).iter_chunks(element, xml_declaration=xml_declaration)


def to_string(element: Element, *, options: SerializeOptions | None = None, **kwargs: Any) -> str:
    """Serialize *element*; keywords are fields of :class:`SerializeOptions`.

    >>> from svgwriter import Circle
    >>> to_string(Circle(5, 5, 2), xml_declaration=False, pretty=False)
    '<circle cx="5" cy="5" r="2"/>'
    """
    return Writer(options, **kwargs).to_string(element)


def write(element: Element, target: AnyPath | TextSink, **kwargs: Any) -> None:
    """Write *element* to a path or text stream; keywords as in :func:`to_string`."""
    options = kwargs.pop("options", None)
    Writer(options, **kwargs).write(element, target)
