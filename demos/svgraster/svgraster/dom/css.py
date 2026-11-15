"""A small CSS parser: declarations, rule sets and simple selectors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMPOUND_RE = re.compile(r"(\*|[a-zA-Z][\w-]*)?((?:[#.][\w-]+)*)$")
_SIMPLE_RE = re.compile(r"([#.])([\w-]+)")
_IMPORTANT = "!important"
ID_WEIGHT = 100
CLASS_WEIGHT = 10
TYPE_WEIGHT = 1


class StyledNode(Protocol):
    """What selector matching needs from a node."""

    tag: str
    parent: StyledNode | None

    @property
    def id(self) -> str | None: ...

    @property
    def classes(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class Declaration:
    """One ``name: value`` pair."""

    name: str
    value: str
    important: bool = False


@dataclass(frozen=True)
class Compound:
    """A compound selector like ``rect.a#b``."""

    tag: str | None = None
    id: str | None = None
    classes: frozenset[str] = frozenset()

    def matches(self, node: StyledNode) -> bool:
        """Whether ``node`` satisfies every part."""
        if self.tag is not None and self.tag != node.tag:
            return False
        if self.id is not None and self.id != node.id:
            return False
        return self.classes <= node.classes

    @property
    def specificity(self) -> int:
        """The specificity contribution."""
        return (ID_WEIGHT if self.id else 0) + CLASS_WEIGHT * len(self.classes) + (TYPE_WEIGHT if self.tag else 0)


@dataclass(frozen=True)
class Selector:
    """A chain of compounds joined by descendant (`` ``) or child (``>``) combinators."""

    parts: tuple[tuple[str, Compound], ...]

    @property
    def specificity(self) -> int:
        """The total specificity."""
        return sum(c.specificity for _, c in self.parts)

    def matches(self, node: StyledNode) -> bool:
        """Match right to left."""
        return _match_from(self.parts, len(self.parts) - 1, node)


def _match_from(parts, index: int, node) -> bool:
    combinator, compound = parts[index]
    if not compound.matches(node):
        return False
    if index == 0:
        return True
    parent = node.parent
    if combinator == ">":
        return parent is not None and _match_from(parts, index - 1, parent)
    while parent is not None:
        if _match_from(parts, index - 1, parent):
            return True
        parent = parent.parent
    return False


@dataclass(frozen=True)
class Rule:
    """A selector with its declarations and source order."""

    selector: Selector
    declarations: tuple[Declaration, ...]
    order: int = 0


@dataclass
class Stylesheet:
    """An ordered list of rules."""

    rules: list[Rule] = field(default_factory=list)

    def extend(self, text: str) -> None:
        """Parse ``text`` and append its rules."""
        for selector, decls in _iter_rule_sets(text):
            self.rules.append(Rule(selector, decls, len(self.rules)))

    def matching(self, node: StyledNode) -> list[Rule]:
        """Rules matching ``node`` sorted by specificity, then order."""
        found = [r for r in self.rules if r.selector.matches(node)]
        found.sort(key=lambda r: (r.selector.specificity, r.order))
        return found


def parse_declarations(text: str) -> list[Declaration]:
    """Parse the body of a ``style`` attribute or rule set."""
    out = []
    for chunk in _COMMENT_RE.sub("", text).split(";"):
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        value = value.strip()
        important = value.lower().endswith(_IMPORTANT)
        if important:
            value = value[: -len(_IMPORTANT)].strip()
        name = name.strip().lower()
        if name and value:
            out.append(Declaration(name, value, important))
    return out


def parse_selector(text: str) -> Selector | None:
    """Parse a single selector; ``None`` when it uses unsupported syntax."""
    tokens = text.replace(">", " > ").split()
    parts: list[tuple[str, Compound]] = []
    combinator = " "
    for token in tokens:
        if token == ">":
            combinator = ">"
            continue
        match = _COMPOUND_RE.match(token)
        if not match:
            return None
        tag = match.group(1)
        ident = None
        classes = set()
        for kind, name in _SIMPLE_RE.findall(match.group(2)):
            if kind == "#":
                ident = name
            else:
                classes.add(name)
        parts.append((combinator, Compound(None if tag in (None, "*") else tag, ident, frozenset(classes))))
        combinator = " "
    return Selector(tuple(parts)) if parts else None


def _strip_at_rules(text: str) -> str:
    out, depth, i = [], 0, 0
    while i < len(text):
        if depth == 0 and text[i] == "@":
            end = text.find(";", i)
            brace = text.find("{", i)
            if brace != -1 and (end == -1 or brace < end):
                depth, i = 1, brace + 1
                while i < len(text) and depth:
                    depth += {"{": 1, "}": -1}.get(text[i], 0)
                    i += 1
                continue
            i = len(text) if end == -1 else end + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _iter_rule_sets(text: str):
    text = _strip_at_rules(_COMMENT_RE.sub("", text))
    for block in text.split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        decls = tuple(parse_declarations(body))
        for raw in head.split(","):
            selector = parse_selector(raw.strip())
            if selector is not None:
                yield selector, decls
