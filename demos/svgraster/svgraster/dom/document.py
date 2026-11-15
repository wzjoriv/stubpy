"""Loading an SVG document into a styled :class:`Node` tree."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .css import Stylesheet
from .node import Node
from .style import specified_style

SVG_SOURCE = str | bytes | os.PathLike
_URL_RE = re.compile(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)")
_BOM = "﻿"
_TEXT_START = ("<", _BOM + "<")
_BYTES_START = (b"<", _BOM.encode("utf-8") + b"<")


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1] if name.startswith("{") else name.split(":", 1)[-1]


def _build(elem: ET.Element, parent: Node | None) -> Node:
    attrs = {_local(k): v for k, v in elem.attrib.items()}
    node = Node(_local(elem.tag), attrs, parent, elem.text or "", elem.tail or "")
    for child in elem:
        if isinstance(child.tag, str):
            node.children.append(_build(child, node))
    return node


def read_source(source: SVG_SOURCE) -> bytes:
    """Return the document bytes from markup or a file path."""
    if isinstance(source, bytes):
        if source.lstrip().startswith(_BYTES_START):
            return source
        return Path(os.fsdecode(source)).read_bytes()
    if isinstance(source, str):
        if source.lstrip().startswith(_TEXT_START):
            return source.encode("utf-8")
        return Path(source).read_bytes()
    return Path(source).read_bytes()


def reference_id(value: str | None) -> str | None:
    """The id in ``url(#id)`` or ``#id``; ``None`` otherwise."""
    if not value:
        return None
    value = value.strip()
    match = _URL_RE.match(value)
    if match:
        return match.group(1)
    if value.startswith("#"):
        return value[1:]
    return None


class Document:
    """A parsed SVG document with an id index and computed styles."""

    def __init__(self, root: Node):
        if root.tag != "svg":
            raise ValueError(f"root element is <{root.tag}>, expected <svg>")
        self.root = root
        self.ids: dict[str, Node] = {}
        self.stylesheet = Stylesheet()
        for node in root.iter():
            if node.id and node.id not in self.ids:
                self.ids[node.id] = node
            if node.tag == "style":
                self.stylesheet.extend(node.text)
        for node in root.iter():
            node.specified = specified_style(node, self.stylesheet)
        root.recompute_style(None)

    @classmethod
    def parse(cls, source: SVG_SOURCE) -> Document:
        """Parse markup (``str``/``bytes``) or a path to a file."""
        try:
            elem = ET.fromstring(read_source(source))
        except ET.ParseError as exc:
            raise ValueError(f"malformed SVG: {exc}") from exc
        return cls(_build(elem, None))

    def lookup(self, ref: str | None, *tags: str) -> Node | None:
        """Resolve ``url(#id)`` / ``#id``, optionally restricted to ``tags``."""
        ident = reference_id(ref)
        node = self.ids.get(ident) if ident else None
        if node is not None and tags and node.tag not in tags:
            return None
        return node

    def href_chain(self, node: Node, limit: int = 32) -> list[Node]:
        """``node`` followed by the elements it inherits from via ``href``."""
        chain = [node]
        while len(chain) < limit:
            target = self.lookup(chain[-1].href)
            if target is None or target in chain:
                break
            chain.append(target)
        return chain
