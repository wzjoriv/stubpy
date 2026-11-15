"""Text content: characters with their owners, ``xml:space`` handling and position lists."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...dom.node import Node
from ...dom.units import parse_length, parse_numbers

TEXT_CONTAINERS = frozenset({"tspan", "a", "altGlyph", "textPath", "tref"})
POSITION_ATTRS = (("x", "x"), ("y", "y"), ("dx", "x"), ("dy", "y"))
PRESERVE = "preserve"


@dataclass
class Char:
    """One addressable character and everything that positions it."""

    text: str
    owner: Node
    chain: tuple[Node, ...]
    preserve: bool = False
    x: float | None = None
    y: float | None = None
    dx: float = 0.0
    dy: float = 0.0
    rotate: float | None = None
    path: Node | None = None
    attrs: dict = field(default_factory=dict)


def _text_of(node: Node) -> str:
    return node.text + "".join(_text_of(c) + c.tail for c in node.children)


def _space_mode(node: Node, inherited: bool) -> bool:
    value = node.get("space")
    return inherited if value is None else value == PRESERVE


def _raw(node: Node, chain: tuple[Node, ...], preserve: bool, path: Node | None, document, out: list[Char]):
    preserve = _space_mode(node, preserve)
    chain = chain + (node,)
    if node.tag == "textPath":
        path = node
    if node.tag == "tref":
        ref = document.lookup(node.href) if document is not None else None
        text = _text_of(ref) if ref is not None else ""
        out.extend(Char(ch, node, chain, preserve, path=path) for ch in text)
        return
    out.extend(Char(ch, node, chain, preserve, path=path) for ch in node.text)
    for child in node.children:
        if child.tag in TEXT_CONTAINERS and child.style.get("display") != "none":
            _raw(child, chain, preserve, path, document, out)
        out.extend(Char(ch, node, chain, preserve, path=path) for ch in child.tail)


def _collapse(chars: list[Char]) -> list[Char]:
    out: list[Char] = []
    for c in chars:
        if c.preserve:
            c.text = " " if c.text in "\n\r\t" else c.text
            out.append(c)
            continue
        if c.text in "\n\r":
            continue
        if c.text == "\t":
            c.text = " "
        if c.text == " " and (not out or (out[-1].text == " " and not out[-1].preserve)):
            continue
        out.append(c)
    while out and out[-1].text == " " and not out[-1].preserve:
        out.pop()
    return out


def _lengths(node: Node, name: str, axis: str, viewport) -> list[float]:
    raw = node.get(name)
    if not raw or not raw.strip():
        return []
    units = node.units(viewport)
    return [parse_length(v, units, axis) for v in raw.replace(",", " ").split()]


def _assign(node: Node, chars: list[Char], viewport) -> None:
    mine = [c for c in chars if node in c.chain]
    if not mine:
        return
    for name, axis in POSITION_ATTRS:
        for c, v in zip(mine, _lengths(node, name, axis, viewport)):
            setattr(c, name, v)
    rotations = parse_numbers(node.get("rotate"))
    if rotations:
        for i, c in enumerate(mine):
            c.rotate = rotations[min(i, len(rotations) - 1)]


def collect(text: Node, viewport, document=None) -> list[Char]:
    """The addressable characters of a ``text`` element with positions resolved."""
    raw: list[Char] = []
    _raw(text, (), False, None, document, raw)
    chars = _collapse(raw)
    for node in text.iter():
        if node is text or (node.tag in TEXT_CONTAINERS and any(node in c.chain for c in chars)):
            if node.tag != "textPath":
                _assign(node, chars, viewport)
    return chars
