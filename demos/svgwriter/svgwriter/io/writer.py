"""Serialization of element trees to SVG text."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import InitVar, dataclass, field
from typing import IO, Any

from .._internal._constants import DEFAULT_INDENT, DEFAULT_PRECISION, DOCTYPE, SVG_NS, XLINK_NS
from .._internal._escape import escape_attribute, escape_text
from .._internal._sentinels import MISSING, MissingType
from .._internal._typing import AnyPath
from ..attributes.protocols import TextSink
from ..attributes.values import format_value
from ..elements.base import Category, Element
from ..elements.unknown import UnknownElement
from ..path.data import PathData

__all__ = ["SerializeOptions", "Writer", "iter_chunks", "to_string", "write"]

DEFAULT_ENCODING = "utf-8"


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
    doctype : bool
        Emit the SVG 1.1 DOCTYPE.
    encoding : str
        Declared and used when writing files.
    compact_paths : bool
        Write path data in its shortest form.
    namespaces : dict
        Namespace declarations put on a root ``<svg>``.
    """

    pretty: InitVar[bool] = True
    indent: str = DEFAULT_INDENT
    precision: int = DEFAULT_PRECISION
    xml_declaration: bool = True
    doctype: bool = False
    encoding: str = DEFAULT_ENCODING
    compact_paths: bool = False
    namespaces: dict[str, str] = field(default_factory=_default_namespaces)
    newline: str = field(init=False, default="\n")

    def __post_init__(self, pretty: bool) -> None:
        if not pretty:
            self.indent = ""
            self.newline = ""


def _inline(element: Element) -> bool:
    return element.category is Category.TEXT_CONTENT or any(isinstance(c, str) for c in element.children)


def _uses_xlink(element: Element) -> bool:
    return any(key.startswith("xlink:") for node in element.iter() for key in node.attributes)


class Writer:
    """Turns an element tree into text, honoring :class:`SerializeOptions`."""

    def __init__(self, options: SerializeOptions | None = None, **kwargs: Any) -> None:
        self.options = options if options is not None else SerializeOptions(**kwargs)

    def _value(self, name: str, value: Any) -> str:
        if self.options.compact_paths and isinstance(value, PathData):
            return value.svg_value(self.options.precision, compact=True)
        return format_value(value, self.options.precision)

    def _open_tag(self, element: Element, extra: dict[str, str]) -> str:
        attributes = {**extra, **{k: self._value(k, v) for k, v in element.attributes.items()}}
        parts = [element.tag] + [f'{k}="{escape_attribute(v)}"' for k, v in attributes.items()]
        return "<" + " ".join(parts)

    def _root_namespaces(self, element: Element) -> dict[str, str]:
        if element.tag == "svg" and not isinstance(element, UnknownElement):
            declared = dict(self.options.namespaces)
            if not _uses_xlink(element):
                declared.pop("xmlns:xlink", None)
            return declared
        return {"xmlns:xlink": XLINK_NS} if _uses_xlink(element) else {}

    def _element(self, element: Element, depth: int, extra: dict[str, str], inline: bool) -> Iterator[str]:
        opts = self.options
        pad = "" if inline else opts.indent * depth
        yield pad + self._open_tag(element, extra)
        if not element.children:
            yield "/>"
            return
        yield ">"
        inner_inline = inline or _inline(element)
        namespace = getattr(element, "namespace", None)
        for child in element.children:
            if isinstance(child, str):
                yield escape_text(child)
                continue
            child_ns = getattr(child, "namespace", None)
            declare = {"xmlns": child_ns} if child_ns and child_ns != namespace else {}
            if not inner_inline:
                yield opts.newline
            yield from self._element(child, depth + 1, declare, inner_inline)
        if not inner_inline:
            yield opts.newline + pad
        yield f"</{element.tag}>"

    def iter_chunks(self, element: Element, *, xml_declaration: bool | MissingType = MISSING) -> Iterator[str]:
        """Yield the document in pieces (useful for streaming)."""
        opts = self.options
        declaration = opts.xml_declaration if xml_declaration is MISSING else xml_declaration
        if declaration:
            yield f'<?xml version="1.0" encoding="{opts.encoding}" standalone="no"?>{opts.newline or chr(10)}'
        if opts.doctype:
            yield DOCTYPE + (opts.newline or "\n")
        yield from self._element(element, 0, self._root_namespaces(element), False)
        if opts.newline:
            yield opts.newline

    def to_string(self, element: Element, **kwargs: Any) -> str:
        return "".join(self.iter_chunks(element, **kwargs))

    def write(self, element: Element, target: AnyPath | TextSink, **kwargs: Any) -> None:
        """Write to a filesystem path or any object with ``write(str)``."""
        if isinstance(target, (str, os.PathLike)):
            self._write_path(element, target, **kwargs)
        elif isinstance(target, TextSink):
            self._write_stream(element, target, **kwargs)
        else:
            raise TypeError(f"cannot write to {type(target).__name__}")

    def _write_path(self, element: Element, path: AnyPath, **kwargs: Any) -> None:
        with _open_text(path, self.options.encoding) as stream:
            self._write_stream(element, stream, **kwargs)

    def _write_stream(self, element: Element, stream: TextSink, **kwargs: Any) -> None:
        for chunk in self.iter_chunks(element, **kwargs):
            stream.write(chunk)


@contextmanager
def _open_text(path: AnyPath, encoding: str) -> Iterator[IO[str]]:
    with open(path, "w", encoding=encoding, newline="\n") as handle:
        yield handle


def iter_chunks(element: Element, **kwargs: Any) -> Iterator[str]:
    """Module-level shortcut for :meth:`Writer.iter_chunks`."""
    xml_declaration = kwargs.pop("xml_declaration", MISSING)
    return Writer(**kwargs).iter_chunks(element, xml_declaration=xml_declaration)


def to_string(element: Element, *, options: SerializeOptions | None = None, **kwargs: Any) -> str:
    """Serialize *element*.

    Parameters
    ----------
    element : Element
        Root of the tree to write.
    options : SerializeOptions, optional
        Pre-built options; otherwise keywords build one.
    **kwargs
        Fields of :class:`SerializeOptions` (``pretty``, ``precision``...).

    Examples
    --------
    >>> from svgwriter import Circle
    >>> to_string(Circle(5, 5, 2), xml_declaration=False, pretty=False)
    '<circle cx="5" cy="5" r="2"/>'
    """
    return Writer(options, **kwargs).to_string(element)


def write(element: Element, target: AnyPath | TextSink, **kwargs: Any) -> None:
    """Write *element* to a path or text stream; keywords as in :func:`to_string`."""
    options = kwargs.pop("options", None)
    Writer(options, **kwargs).write(element, target)
