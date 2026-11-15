"""A small CSS parser: declarations, rule sets, ``@font-face`` and CSS2/3 selectors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ._selectors import Selector, parse_selector_list

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_IMPORTANT = "!important"
SCREEN_MEDIA = frozenset({"all", "screen"})
MAX_IMPORT_DEPTH = 8
_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*)?['\"]?([^'\")\s;]+)['\"]?\s*\)?\s*([^;]*);", re.IGNORECASE)


@dataclass(frozen=True)
class Declaration:
    """One ``name: value`` pair."""

    name: str
    value: str
    important: bool = False


@dataclass(frozen=True)
class Rule:
    """A selector with its declarations and source order."""

    selector: Selector
    declarations: tuple[Declaration, ...]
    order: int = 0


@dataclass
class Stylesheet:
    """An ordered list of rules plus the ``@font-face`` blocks."""

    rules: list[Rule] = field(default_factory=list)
    font_faces: list[dict[str, str]] = field(default_factory=list)

    def extend(self, text: str, base_dir: Path | None = None, depth: int = 0) -> None:
        """Parse ``text`` and append its rules; local ``@import`` files resolve against ``base_dir``."""
        text = _COMMENT_RE.sub("", text)
        if base_dir is not None and depth < MAX_IMPORT_DEPTH:
            for match in _IMPORT_RE.finditer(text):
                href, media = match.group(1), match.group(2).strip().lower()
                if ":" in href.split("/")[0] or (media and not SCREEN_MEDIA & {m.strip() for m in media.split(",")}):
                    continue
                path = base_dir / href
                try:
                    imported = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.extend(imported, path.parent, depth + 1)
        for selector, decls in _iter_rule_sets(text, self.font_faces):
            self.rules.append(Rule(selector, decls, len(self.rules)))

    def matching(self, node) -> list[Rule]:
        """Rules matching ``node`` sorted by specificity, then order."""
        found = [r for r in self.rules if r.selector.matches(node)]
        found.sort(key=lambda r: (r.selector.specificity, r.order))
        return found


def parse_declarations(text: str) -> list[Declaration]:
    """Parse the body of a ``style`` attribute or rule set."""
    out = []
    for chunk in _split_outside_parens(_COMMENT_RE.sub("", text), ";"):
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


def _split_outside_parens(text: str, sep: str) -> list[str]:
    parts, depth, quote, start = [], 0, "", 0
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def parse_selector(text: str) -> Selector | None:
    """Parse a single selector; ``None`` when it uses unsupported syntax."""
    found = parse_selector_list(text)
    return found[0] if len(found) == 1 else None


def _block_end(text: str, start: int) -> int:
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return i


def _flatten_at_rules(text: str, font_faces: list[dict[str, str]]) -> str:
    """Drop at-rules, keeping ``@media all/screen`` bodies and collecting ``@font-face``."""
    out, i = [], 0
    while i < len(text):
        if text[i] != "@":
            out.append(text[i])
            i += 1
            continue
        end = text.find(";", i)
        brace = text.find("{", i)
        if brace == -1 or (end != -1 and end < brace):
            i = len(text) if end == -1 else end + 1
            continue
        close = _block_end(text, brace + 1)
        head = text[i + 1:brace].strip().lower()
        body = text[brace + 1:close - 1]
        if head == "font-face":
            font_faces.append({d.name: d.value for d in parse_declarations(body)})
        elif head.startswith("media") and SCREEN_MEDIA & {m.strip() for m in head[5:].split(",")}:
            out.append(_flatten_at_rules(body, font_faces))
        i = close
    return "".join(out)


def _iter_rule_sets(text: str, font_faces: list[dict[str, str]]):
    text = _flatten_at_rules(_COMMENT_RE.sub("", text), font_faces)
    for block in text.split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        decls = tuple(parse_declarations(body))
        for selector in parse_selector_list(head):
            yield selector, decls
