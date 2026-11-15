"""Read SVG text back into the element model using ``xml.etree``."""

from __future__ import annotations

import enum
import warnings
import xml.etree.ElementTree as ET
from typing import Final

from .._internal._constants import SVG_NS, XLINK_NS, XML_NS
from .._internal._typing import AnyPath
from ..elements.base import Category, ContentModel, Element
from ..elements.unknown import UnknownElement

__all__ = ["SVGParseError", "Strictness", "parse", "parse_file"]

_PREFIXES: Final = {XLINK_NS: "xlink", XML_NS: "xml"}


class Strictness(enum.IntEnum):
    """How to treat unknown elements and foreign attributes."""

    LENIENT = 0
    WARN = 1
    STRICT = 2


class SVGParseError(ValueError):
    """Raised for malformed input or, when strict, unsupported content."""


def _split(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return namespace, local
    return None, name


def _complain(message: str, strictness: Strictness) -> None:
    if strictness is Strictness.STRICT:
        raise SVGParseError(message)
    if strictness is Strictness.WARN:
        warnings.warn(message, stacklevel=4)


def _keeps_whitespace(element: Element) -> bool:
    return element.category is Category.TEXT_CONTENT or element.content is ContentModel.TEXT


def _add_text(element: Element, text: str | None) -> None:
    if not text or (not text.strip() and not _keeps_whitespace(element)):
        return
    if element.children and isinstance(element.children[-1], str):
        element.children[-1] += text
    else:
        element.children.append(text)


def _convert(node: ET.Element, strictness: Strictness) -> Element:
    namespace, local = _split(node.tag)
    attributes: dict[str, str] = {}
    for key, value in node.attrib.items():
        key_ns, key_local = _split(key)
        if key_ns is None:
            attributes[key_local] = value
        elif key_ns in _PREFIXES:
            attributes[f"{_PREFIXES[key_ns]}:{key_local}"] = value
        else:
            _complain(f"dropping foreign attribute {key!r}", strictness)

    cls = Element.lookup(local) if namespace in (SVG_NS, None) else None
    element: Element
    if cls is None:
        if namespace in (SVG_NS, None):
            _complain(f"unknown SVG element <{local}>", strictness)
        element = UnknownElement(local, namespace=None if namespace == SVG_NS else namespace)
        element.attributes.update(attributes)
    else:
        element = cls.from_attributes(attributes)

    _add_text(element, node.text)
    for child_node in node:
        child = _convert(child_node, strictness)
        child.parent = element
        element.children.append(child)
        _add_text(element, child_node.tail)
    return element


def parse(source: str | bytes, *, strictness: Strictness = Strictness.LENIENT) -> Element:
    """Parse SVG text into an element tree.

    Parameters
    ----------
    source : str or bytes
        The document. A DOCTYPE and XML declaration are accepted.
    strictness : Strictness
        What to do with unknown elements and foreign attributes.

    Returns
    -------
    Element
        The root, usually an :class:`~svgwriter.elements.Svg`.
    """
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise SVGParseError(str(exc)) from exc
    return _convert(root, strictness)


def parse_file(path: AnyPath, *, strictness: Strictness = Strictness.LENIENT) -> Element:
    """Parse an SVG file."""
    with open(path, "rb") as handle:
        return parse(handle.read(), strictness=strictness)
