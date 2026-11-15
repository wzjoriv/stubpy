"""CSS selectors: type, id, class, attribute, pseudo-class and the four combinators."""
from __future__ import annotations

import re
from dataclasses import dataclass

ATTR_OPS = ("~=", "|=", "^=", "$=", "*=", "=")
DESCENDANT, CHILD, ADJACENT, SIBLING = " ", ">", "+", "~"
NEVER_MATCH = frozenset({"hover", "active", "focus", "visited", "target", "checked", "disabled", "enabled"})
STRUCTURAL = frozenset({"first-child", "last-child", "only-child", "root", "empty", "link"})
_IDENT = r"-?[_a-zA-Z\u00a0-\uffff][\w\-\u00a0-\uffff]*"
_NTH_RE = re.compile(r"^\s*(?:([+-]?\d*)n\s*(?:([+-])\s*(\d+))?|([+-]?\d+)|(odd|even))\s*$")


class SelectorError(ValueError):
    """Raised for selectors this parser does not understand."""


@dataclass(frozen=True)
class Compound:
    """A compound selector such as ``rect.a#b[x]:first-child``."""

    tag: str | None = None
    id: str | None = None
    classes: frozenset[str] = frozenset()
    attrs: tuple[tuple[str, str | None, str | None], ...] = ()
    pseudos: tuple[tuple[str, str | None], ...] = ()

    @property
    def specificity(self) -> tuple[int, int, int]:
        """``(ids, classes + attributes + pseudo-classes, types)``."""
        return (1 if self.id else 0, len(self.classes) + len(self.attrs) + len(self.pseudos),
                1 if self.tag else 0)

    def matches(self, node) -> bool:
        """Whether ``node`` satisfies every part."""
        if self.tag is not None and self.tag != node.tag:
            return False
        if self.id is not None and self.id != node.id:
            return False
        if not self.classes <= node.classes:
            return False
        return all(_attr_match(node, *a) for a in self.attrs) and all(_pseudo_match(node, *p) for p in self.pseudos)


def _attr_match(node, name: str, op: str | None, value: str | None) -> bool:
    actual = node.attrs.get(name)
    if actual is None:
        return False
    if op is None:
        return True
    if op == "=":
        return actual == value
    if op == "~=":
        return value in actual.split()
    if op == "|=":
        return actual == value or actual.startswith(value + "-")
    if not value:
        return False
    if op == "^=":
        return actual.startswith(value)
    if op == "$=":
        return actual.endswith(value)
    return value in actual


def _siblings(node) -> list:
    return [c for c in node.parent.children] if node.parent is not None else [node]


def _nth(arg: str | None, index: int) -> bool:
    match = _NTH_RE.match(arg or "")
    if not match:
        return False
    a_txt, sign, b_txt, only_b, word = match.groups()
    if word:
        return index % 2 == (1 if word == "odd" else 0)
    if only_b is not None:
        return index == int(only_b)
    a = int(a_txt + "1") if a_txt in ("", "+", "-") else int(a_txt)
    b = int(b_txt or 0) * (-1 if sign == "-" else 1)
    if a == 0:
        return index == b
    return (index - b) % a == 0 and (index - b) // a >= 0


def _lang(node) -> str:
    while node is not None:
        lang = node.attrs.get("lang")
        if lang:
            return lang.lower()
        node = node.parent
    return ""


def _pseudo_match(node, name: str, arg: str | None) -> bool:
    if name in NEVER_MATCH:
        return False
    sibs = _siblings(node)
    if name == "first-child":
        return sibs[0] is node
    if name == "last-child":
        return sibs[-1] is node
    if name == "only-child":
        return len(sibs) == 1
    if name == "root":
        return node.parent is None
    if name == "empty":
        return not node.children and not (node.text or "").strip()
    if name == "link":
        return node.tag == "a" and node.href is not None
    if name == "nth-child":
        return _nth(arg, next(i for i, s in enumerate(sibs) if s is node) + 1)
    if name == "lang":
        want = (arg or "").strip().lower()
        lang = _lang(node)
        return bool(want) and (lang == want or lang.startswith(want + "-"))
    return False


@dataclass(frozen=True)
class Selector:
    """Compounds joined by combinators; ``parts[i] = (combinator before, compound)``."""

    parts: tuple[tuple[str, Compound], ...]

    @property
    def specificity(self) -> tuple[int, int, int]:
        """The summed ``(a, b, c)`` specificity."""
        a = b = c = 0
        for _, comp in self.parts:
            x, y, z = comp.specificity
            a, b, c = a + x, b + y, c + z
        return (a, b, c)

    def matches(self, node) -> bool:
        """Match right to left."""
        return _match_from(self.parts, len(self.parts) - 1, node)


def _previous_siblings(node):
    if node.parent is None:
        return []
    sibs = node.parent.children
    return list(reversed(sibs[:next(i for i, s in enumerate(sibs) if s is node)]))


def _match_from(parts, index: int, node) -> bool:
    combinator, compound = parts[index]
    if not compound.matches(node):
        return False
    if index == 0:
        return True
    if combinator == CHILD:
        return node.parent is not None and _match_from(parts, index - 1, node.parent)
    if combinator == ADJACENT:
        prev = _previous_siblings(node)
        return bool(prev) and _match_from(parts, index - 1, prev[0])
    if combinator == SIBLING:
        return any(_match_from(parts, index - 1, s) for s in _previous_siblings(node))
    parent = node.parent
    while parent is not None:
        if _match_from(parts, index - 1, parent):
            return True
        parent = parent.parent
    return False


class _Scanner:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def ident(self) -> str:
        match = re.compile(_IDENT).match(self.text, self.pos)
        if not match:
            raise SelectorError(f"expected a name at {self.pos} in {self.text!r}")
        self.pos = match.end()
        return match.group(0)

    def until(self, close: str) -> str:
        start, quote = self.pos, ""
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            self.pos += 1
            if quote:
                quote = "" if ch == quote else quote
            elif ch in "'\"":
                quote = ch
            elif ch == close:
                return self.text[start:self.pos - 1]
        raise SelectorError(f"unterminated {close!r} in {self.text!r}")

    def skip_space(self) -> bool:
        start = self.pos
        while self.peek().isspace():
            self.pos += 1
        return self.pos > start


def _attribute(body: str) -> tuple[str, str | None, str | None]:
    for op in ATTR_OPS:
        if op in body:
            name, value = body.split(op, 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return (name.strip().split("|")[-1], op, value)
    return (body.strip().split("|")[-1], None, None)


def _compound(sc: _Scanner) -> Compound:
    tag, ident, classes, attrs, pseudos = None, None, set(), [], []
    if sc.peek() == "*":
        sc.pos += 1
    elif re.compile(_IDENT).match(sc.text, sc.pos):
        tag = sc.ident()
    while True:
        ch = sc.peek()
        if ch == "#":
            sc.pos += 1
            ident = sc.ident()
        elif ch == ".":
            sc.pos += 1
            classes.add(sc.ident())
        elif ch == "[":
            sc.pos += 1
            attrs.append(_attribute(sc.until("]")))
        elif ch == ":":
            sc.pos += 1
            if sc.peek() == ":":
                raise SelectorError("pseudo-elements never match")
            name = sc.ident().lower()
            arg = None
            if sc.peek() == "(":
                sc.pos += 1
                arg = sc.until(")")
            if name not in NEVER_MATCH | STRUCTURAL | {"lang", "nth-child"}:
                raise SelectorError(f"unsupported pseudo-class :{name}")
            pseudos.append((name, arg))
        else:
            break
    return Compound(tag, ident, frozenset(classes), tuple(attrs), tuple(pseudos))


def parse_one(text: str) -> Selector:
    """Parse one complex selector or raise :class:`SelectorError`."""
    sc = _Scanner(text.strip())
    parts: list[tuple[str, Compound]] = []
    combinator = DESCENDANT
    while sc.peek():
        start = sc.pos
        parts.append((combinator, _compound(sc)))
        if sc.pos == start:
            raise SelectorError(f"unexpected {sc.peek()!r} in {text!r}")
        spaced = sc.skip_space()
        if sc.peek() in (CHILD, ADJACENT, SIBLING):
            combinator = sc.peek()
            sc.pos += 1
            sc.skip_space()
        elif spaced:
            combinator = DESCENDANT
        elif sc.peek():
            raise SelectorError(f"unexpected {sc.peek()!r} in {text!r}")
    if not parts:
        raise SelectorError("empty selector")
    return Selector(tuple(parts))


def parse_selector_list(text: str) -> list[Selector]:
    """The selectors of a comma-separated group, skipping unsupported ones."""
    out, depth, start, pieces = [], 0, 0, []
    for i, ch in enumerate(text):
        depth += {"[": 1, "(": 1, "]": -1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            pieces.append(text[start:i])
            start = i + 1
    pieces.append(text[start:])
    for raw in pieces:
        try:
            out.append(parse_one(raw))
        except SelectorError:
            continue
    return out
