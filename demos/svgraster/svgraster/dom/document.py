"""Loading an SVG document into a styled :class:`Node` tree."""
from __future__ import annotations

import gzip
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

from .css import Stylesheet
from .node import Node
from .style import specified_style

SVG_SOURCE = str | bytes | os.PathLike
GZIP_MAGIC = b"\x1f\x8b"
SOURCE_METHODS = ("__svg__", "to_string", "tostring")
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
_URL_RE = re.compile(r"url\(\s*['\"]?#([^)'\"]+)['\"]?\s*\)")
_EXTERNAL_RE = re.compile(r"^\s*(?:url\(\s*['\"]?)?([^#'\"()]+)#([^)'\"\s]+)['\"]?\s*\)?\s*$")
_PI_RE = re.compile(r"<\?xml-stylesheet\s+(.*?)\?>", re.DOTALL)
_PI_ATTR_RE = re.compile(r"(\w+)\s*=\s*[\"']([^\"']*)[\"']")
REMOTE_PREFIXES = ("http:", "https:", "ftp:", "data:")
EXTERNAL_KEY = "external-documents"
OWNER_KEY = "external-owners"
MEMBERS_KEY = "members"
_BOM = "﻿"
_TEXT_START = ("<", _BOM + "<")
_BYTES_START = (b"<", _BOM.encode("utf-8") + b"<")


def _split(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        ns, local = name[1:].split("}", 1)
        return ns, local
    return None, name


def _tag(name: str) -> str:
    """Element name: SVG (or un-namespaced) elements keep their local name, others stay qualified."""
    ns, local = _split(name)
    return local if ns in (None, SVG_NS) else f"{{{ns}}}{local}"


def _attribute(name: str) -> str:
    """Attribute name: plain, XLink and XML attributes by local name; foreign ones stay qualified."""
    ns, local = _split(name)
    if ns is None or ns in (XLINK_NS, XML_NS, SVG_NS):
        return local.split(":", 1)[-1]
    return f"{{{ns}}}{local}"


def _build(elem: ET.Element, parent: Node | None) -> Node:
    attrs = {_attribute(k): v for k, v in elem.attrib.items()}
    node = Node(_tag(elem.tag), attrs, parent, elem.text or "", elem.tail or "")
    for child in elem:
        if isinstance(child.tag, str):
            node.children.append(_build(child, node))
        elif node.children:
            node.children[-1].tail += child.tail or ""
        else:
            node.text += child.tail or ""
    return node


def _markup_of(source) -> str | bytes | None:
    for name in SOURCE_METHODS:
        method = getattr(source, name, None)
        if callable(method):
            return method()
    return None


def _is_markup(source: str | bytes) -> bool:
    if isinstance(source, str):
        return source.lstrip().startswith(_TEXT_START)
    return source.lstrip().startswith(_BYTES_START) or source[:2] == GZIP_MAGIC


def source_path(source) -> Path | None:
    """The file path ``source`` refers to, or ``None`` for markup and objects."""
    if isinstance(source, os.PathLike):
        return Path(source)
    if isinstance(source, bytes) and not _is_markup(source):
        return Path(os.fsdecode(source))
    if isinstance(source, str) and not _is_markup(source):
        return Path(source)
    return None


def read_source(source) -> bytes:
    """Document bytes from markup, a path, gzip data (``.svgz``) or an object with ``__svg__()``/``to_string()``."""
    if not isinstance(source, (str, bytes, os.PathLike)):
        markup = _markup_of(source)
        if markup is None:
            raise TypeError(f"cannot render {type(source).__name__}: expected markup, a path, or an object "
                            "with __svg__() or to_string()")
        if not _is_markup(markup):
            raise ValueError(f"{type(source).__name__} did not produce SVG markup")
        source = markup
    path = source_path(source)
    if path is not None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(f"SVG file not found: {path}") from None
    else:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    if data[:2] == GZIP_MAGIC:
        data = gzip.decompress(data)
    return data


def _linked_css(data: bytes, base: Path) -> list[str]:
    """Local CSS files named by ``<?xml-stylesheet type="text/css" href="..."?>`` instructions."""
    out = []
    head = data[:data.find(b"<svg")] if b"<svg" in data else b""
    for match in _PI_RE.finditer(head.decode("utf-8", "replace")):
        attrs = dict(_PI_ATTR_RE.findall(match.group(1)))
        href = attrs.get("href", "")
        if attrs.get("type", "text/css") != "text/css" or not href or ":" in href.split("/")[0]:
            continue
        try:
            out.append((base / href).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return out


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
    """A parsed SVG document with an id index, computed styles and a base folder."""

    def __init__(self, root: Node, base_dir: str | os.PathLike | None = None,
                 stylesheet: Stylesheet | None = None, extra_css: tuple[str, ...] = ()):
        if root.tag != "svg":
            raise ValueError(f"root element is <{root.tag}>, expected <svg>")
        self.root = root
        self.base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self.ids: dict[str, Node] = {}
        self.stylesheet = stylesheet if stylesheet is not None else Stylesheet()
        for css in extra_css:
            self.stylesheet.extend(css)
        for node in root.iter():
            if node.id and node.id not in self.ids:
                self.ids[node.id] = node
            if node.tag == "style" and stylesheet is None and node.get("type", "text/css") == "text/css":
                self.stylesheet.extend(node.text, self.base_dir)
        for node in root.iter():
            node.specified = specified_style(node, self.stylesheet)
        root.recompute_style(None)
        self.cache: dict = {}
        self.external_ids: dict[str, Node] = {}

    def __repr__(self) -> str:
        return f"<Document {len(self.ids)} ids, base_dir={str(self.base_dir)!r}>"

    @classmethod
    def parse(cls, source, base_dir: str | os.PathLike | None = None) -> Document:
        """Parse markup, a path, gzip data or an object with ``__svg__()``/``to_string()``.

        ``base_dir`` resolves relative ``href``/``url()`` references; it defaults to the
        file's folder, or the working directory for markup.
        """
        if isinstance(source, Document):
            return source
        data = read_source(source)
        path = source_path(source) if isinstance(source, (str, bytes, os.PathLike)) else None
        if base_dir is None and path is not None:
            base_dir = path.resolve().parent
        try:
            elem = ET.fromstring(data)
        except ET.ParseError as exc:
            where = f" in {path}" if path is not None else ""
            raise ValueError(f"malformed SVG{where}: {exc}") from exc
        base = Path(base_dir) if base_dir is not None else Path.cwd()
        return cls(_build(elem, None), base_dir, extra_css=tuple(_linked_css(data, base)))

    def derive(self, root: Node) -> Document:
        """A document for a modified copy of this tree, sharing the stylesheet and base folder."""
        return Document(root, self.base_dir, self.stylesheet)

    def resolve(self, href: str) -> Path:
        """A local file reference (plain path or ``file:`` URL) relative to :attr:`base_dir`."""
        if href.startswith("file:"):
            href = unquote(urlparse(href).path)
            if os.name == "nt" and len(href) > 2 and href[0] == "/" and href[2] == ":":
                href = href[1:]
        path = Path(unquote(href))
        return path if path.is_absolute() else self.base_dir / path

    def lookup(self, ref: str | None, *tags: str) -> Node | None:
        """Resolve ``url(#id)`` / ``#id``, optionally restricted to ``tags``."""
        ident = reference_id(ref)
        if ident:
            node = self.ids.get(ident) or self.external_ids.get(ident)
        else:
            node = self._external(ref)
        if node is not None and tags and node.tag not in tags:
            return None
        return node

    def contains(self, node: Node) -> bool:
        """Whether ``node`` is an element of this document's own tree."""
        members = self.cache.get(MEMBERS_KEY)
        if members is None:
            members = self.cache[MEMBERS_KEY] = {id(n) for n in self.root.iter()}
        return id(node) in members

    def owner_of(self, node: Node) -> Document:
        """The document ``node`` belongs to: this one, or a referenced external document."""
        return self.cache.get(OWNER_KEY, {}).get(id(node), self)

    def _external(self, ref: str | None) -> Node | None:
        """An element in another local document, ``file.svg#id``; its ids become fallbacks here."""
        match = _EXTERNAL_RE.match(ref or "")
        if not match or match.group(1).strip().lower().startswith(REMOTE_PREFIXES):
            return None
        path = self.resolve(match.group(1).strip())
        docs = self.cache.setdefault(EXTERNAL_KEY, {})
        key = str(path)
        if key not in docs:
            try:
                docs[key] = Document.parse(path)
            except (OSError, ValueError):
                docs[key] = None
            if docs[key] is not None:
                owners = self.cache.setdefault(OWNER_KEY, {})
                for node in docs[key].root.iter():
                    owners[id(node)] = docs[key]
                for ident, node in docs[key].ids.items():
                    self.external_ids.setdefault(ident, node)
                for ident, node in self.ids.items():
                    docs[key].external_ids.setdefault(ident, node)
        doc = docs[key]
        return doc.ids.get(match.group(2)) if doc is not None else None

    def href_chain(self, node: Node, limit: int = 32) -> list[Node]:
        """``node`` followed by the elements it inherits from via ``href``."""
        chain = [node]
        while len(chain) < limit:
            target = self.lookup(chain[-1].href)
            if target is None or target in chain:
                break
            chain.append(target)
        return chain
