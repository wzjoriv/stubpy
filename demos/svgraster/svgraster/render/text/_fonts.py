"""Per-document font resolution: SVG fonts, ``@font-face``, ``font-face`` elements and system faces."""
from __future__ import annotations

import re
import warnings

from ...dom.document import Document
from ...fonts import Font, FontDatabase, FontFormatError, FontMatch, SvgFont, default_database, weight_value
from ...fonts.strokefont import StrokeFont
from ...io.resources import ResourceError, load

_SRC_RE = re.compile(r"(url|local)\(\s*(['\"]?)(.*?)\2\s*\)", re.IGNORECASE)
ITALIC_STYLES = frozenset({"italic", "oblique"})
BOLD_THRESHOLD = 600


class DocumentFonts:
    """Resolves the faces for a text element's computed style, with caching."""

    def __init__(self, document: Document, database: FontDatabase | None = None):
        self.document = document
        self.database = FontDatabase(parent=database or default_database())
        self._cache: dict[tuple[str, int, bool], list[FontMatch]] = {}
        self._stroke: dict[bool, StrokeFont] = {}
        for node in document.root.iter():
            if node.tag == "font":
                face = SvgFont(node)
                self.database.add_font(face, face.family or node.id or "svg-font")
            elif node.tag == "font-face" and (node.parent is None or node.parent.tag != "font"):
                self._font_face_element(node)
        for rule in document.stylesheet.font_faces:
            self._font_face_rule(rule)

    def _register(self, href: str, family: str, weight: int | None, italic: bool | None) -> bool:
        try:
            res = load(href, self.document)
        except ResourceError as exc:
            warnings.warn(f"svgraster: font {href!r}: {exc}", stacklevel=2)
            return False
        if res.media_type == "image/svg+xml":
            sub = Document.parse(res.data, base_dir=res.path.parent if res.path else None)
            fonts = [n for n in sub.root.iter() if n.tag == "font" and (not res.fragment or n.id == res.fragment)]
            for node in fonts[:1]:
                self.database.add_font(SvgFont(node), family, weight, italic)
            return bool(fonts)
        try:
            self.database.add_font(Font(res.data, 0, str(res.path) if res.path else None), family, weight, italic)
        except (FontFormatError, IndexError, ValueError) as exc:
            warnings.warn(f"svgraster: font {href!r}: {exc}", stacklevel=2)
            return False
        return True

    def _local(self, name: str, family: str, weight, italic) -> bool:
        found = self.database.parent.match_family(name, weight or 400, bool(italic))
        if found is None:
            return False
        self.database.add_font(found.font, family, weight, italic)
        return True

    def _font_face_rule(self, rule: dict[str, str]) -> None:
        family = rule.get("font-family", "").strip().strip("'\"")
        if not family:
            return
        weight = weight_value(rule["font-weight"]) if "font-weight" in rule else None
        italic = rule["font-style"].strip().lower() in ITALIC_STYLES if "font-style" in rule else None
        for kind, _, value in _SRC_RE.findall(rule.get("src", "")):
            ok = (self._register(value, family, weight, italic) if kind.lower() == "url"
                  else self._local(value, family, weight, italic))
            if ok:
                return

    def _font_face_element(self, node) -> None:
        family = (node.get("font-family") or "").strip("'\" ")
        if not family:
            return
        weight = weight_value(node.get("font-weight")) if node.get("font-weight") else None
        italic = (node.get("font-style") or "normal").lower() in ITALIC_STYLES
        for src in (c for c in node.children if c.tag == "font-face-src"):
            for item in src.children:
                if item.tag == "font-face-uri" and item.href and self._register(item.href, family, weight, italic):
                    return
                if item.tag == "font-face-name" and self._local(item.get("name", ""), family, weight, italic):
                    return

    def stroke_font(self, bold: bool) -> StrokeFont:
        """The built-in stroke font in a regular or bold weight."""
        if bold not in self._stroke:
            self._stroke[bold] = StrokeFont(700 if bold else 400)
        return self._stroke[bold]

    def fallback(self, char: str, style: dict[str, str]) -> FontMatch | None:
        """A system face covering ``char`` when none of the requested families do."""
        italic = style.get("font-style", "normal") in ITALIC_STYLES
        return self.database.fallback(char, weight_value(style.get("font-weight")), italic)

    def matches(self, style: dict[str, str]) -> list[FontMatch]:
        """Faces for a computed style, best first, ending with the stroke font."""
        family = style.get("font-family", "sans-serif")
        weight = weight_value(style.get("font-weight"))
        italic = style.get("font-style", "normal") in ITALIC_STYLES
        key = (family, weight, italic)
        if key not in self._cache:
            found = self.database.match(family, weight, italic)
            found.append(FontMatch(self.stroke_font(weight >= BOLD_THRESHOLD), synthetic_oblique=italic))
            self._cache[key] = found
        return self._cache[key]


def document_fonts(document: Document, database: FontDatabase | None = None) -> DocumentFonts:
    """The cached :class:`DocumentFonts` for ``document``."""
    key = ("fonts", id(database))
    fonts = document.cache.get(key)
    if fonts is None:
        fonts = document.cache[key] = DocumentFonts(document, database)
    return fonts
