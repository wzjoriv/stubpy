"""Font discovery and CSS-style family, weight and style matching."""
from __future__ import annotations

import os
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ._reader import FontFormatError
from ._scan import FaceInfo, describe, font_files, system_font_dirs
from .font import Font

NORMAL_WEIGHT = 400
MEDIUM_WEIGHT = 500
BOLD_WEIGHT = 700
SYNTHETIC_BOLD_DELTA = 300
GENERIC_FAMILIES = {
    "serif": ("Times New Roman", "DejaVu Serif", "Liberation Serif", "Noto Serif", "Georgia", "Times",
              "FreeSerif"),
    "sans-serif": ("Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans", "Segoe UI",
                   "FreeSans", "Verdana"),
    "monospace": ("Courier New", "DejaVu Sans Mono", "Liberation Mono", "Consolas", "Menlo", "Noto Sans Mono",
                  "FreeMono"),
    "cursive": ("Comic Sans MS", "Segoe Script", "Apple Chancery", "URW Chancery L"),
    "fantasy": ("Impact", "Papyrus", "Haettenschweiler"),
}
DEFAULT_FAMILY = "sans-serif"
FALLBACK_FAMILIES = (
    "Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Segoe UI Historic", "Microsoft YaHei", "Yu Gothic",
    "MS Gothic", "Malgun Gothic", "Nirmala UI", "Ebrima", "Gadugi", "Leelawadee UI", "Microsoft Himalaya",
    "Arial Unicode MS", "Cambria Math", "DejaVu Sans", "Noto Sans", "Noto Sans CJK SC", "Noto Sans Symbols",
    "Noto Sans Symbols2", "Noto Color Emoji", "PingFang SC", "Hiragino Sans", "Apple Symbols",
    "Apple Color Emoji", "Droid Sans Fallback", "WenQuanYi Micro Hei", "FreeSans", "FreeSerif", "Unifont",
)


@dataclass(frozen=True)
class FontMatch:
    """A matched face and the synthetic styling needed to approximate the request."""

    font: Font
    synthetic_bold: bool = False
    synthetic_oblique: bool = False


def parse_family_list(value: str | Sequence[str] | None) -> list[str]:
    """Split a CSS ``font-family`` value into unquoted names."""
    if value is None:
        return []
    if not isinstance(value, str):
        return [v.strip().strip("'\"") for v in value if v.strip()]
    return [part.strip().strip("'\"").strip() for part in value.split(",") if part.strip().strip("'\"")]


def weight_value(value: str | int | None, parent: int = NORMAL_WEIGHT) -> int:
    """A numeric CSS weight from a keyword or number."""
    if isinstance(value, int):
        return value
    v = (value or "normal").strip().lower()
    if v == "normal":
        return NORMAL_WEIGHT
    if v == "bold":
        return BOLD_WEIGHT
    if v == "bolder":
        return min(900, parent + SYNTHETIC_BOLD_DELTA) if parent < 600 else 900
    if v == "lighter":
        return 100 if parent < 600 else NORMAL_WEIGHT
    try:
        return max(1, min(1000, int(float(v))))
    except ValueError:
        return NORMAL_WEIGHT


def _weight_rank(desired: int, actual: int) -> tuple[int, int]:
    if desired == actual:
        return (0, 0)
    if NORMAL_WEIGHT <= desired <= MEDIUM_WEIGHT:
        if desired < actual <= MEDIUM_WEIGHT:
            return (1, actual - desired)
        if actual < desired:
            return (2, desired - actual)
        return (3, actual - desired)
    if desired < NORMAL_WEIGHT:
        return (1, desired - actual) if actual < desired else (2, actual - desired)
    return (1, actual - desired) if actual > desired else (2, desired - actual)


class FontDatabase:
    """Faces from folders, files and in-memory fonts, matched like CSS.

    ``parent`` is consulted when no face here matches a family.
    """

    def __init__(self, paths: Iterable[str | os.PathLike] = (), *, system: bool = False,
                 parent: FontDatabase | None = None):
        self.parent = parent
        self._faces: list[FaceInfo] = []
        self._memory: dict[tuple[str, int], Font] = {}
        self._loaded: dict[tuple[str, int], Font | None] = {}
        self._fallbacks: dict[tuple[str, int, bool], FontMatch | None] = {}
        self._lock = threading.Lock()
        self._scanned = False
        self._pending: list[Path] = [Path(p) for p in paths]
        self._system = system

    def __repr__(self) -> str:
        return f"<FontDatabase {len(self.faces)} faces>"

    def add_path(self, path: str | os.PathLike) -> None:
        """Add a font file or a folder searched recursively."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"font path not found: {path}")
        with self._lock:
            self._pending.append(path)

    def add_font(self, font: Font, family: str | None = None, weight: int | None = None,
                 italic: bool | None = None) -> None:
        """Register an already loaded face, optionally under another family name."""
        key = (f"<memory:{id(font)}>", len(self._memory))
        fam = family or font.family
        info = FaceInfo(key[0], key[1], fam, weight or font.weight, font.italic if italic is None else italic,
                        frozenset({fam.lower()}))
        with self._lock:
            self._memory[key] = font
            self._faces.insert(0, info)

    def _scan(self) -> None:
        with self._lock:
            roots = self._pending
            self._pending = []
            if self._system and not self._scanned:
                roots = roots + system_font_dirs()
            self._scanned = True
        for root in roots:
            faces = [face for f in font_files(root) for face in describe(f)]
            with self._lock:
                self._faces.extend(faces)

    @property
    def faces(self) -> list[FaceInfo]:
        """Every known face (scanning lazily on first use)."""
        if self._pending or not self._scanned:
            self._scan()
        return list(self._faces)

    def families(self) -> list[str]:
        """Sorted family names, including the parent's."""
        names = {f.family for f in self.faces}
        if self.parent is not None:
            names.update(self.parent.families())
        return sorted(names, key=str.lower)

    def load(self, info: FaceInfo) -> Font | None:
        """The parsed face for ``info`` (cached); ``None`` when it fails to parse."""
        key = info.key
        if key in self._memory:
            return self._memory[key]
        if key not in self._loaded:
            try:
                self._loaded[key] = Font.from_file(info.path, info.index)
            except (OSError, FontFormatError, IndexError, ValueError):
                self._loaded[key] = None
        return self._loaded[key]

    def _candidates(self, family: str) -> list[FaceInfo]:
        name = family.lower()
        return [f for f in self.faces if name in f.aliases]

    def match_family(self, family: str, weight: int = NORMAL_WEIGHT, italic: bool = False) -> FontMatch | None:
        """The best face of one family name (generic names expand), or ``None``."""
        names = GENERIC_FAMILIES.get(family.lower(), (family,))
        for name in names:
            faces = self._candidates(name)
            if faces:
                found = self._pick(faces, weight, italic)
                if found is not None:
                    return found
        if self.parent is not None:
            return self.parent.match_family(family, weight, italic)
        return None

    def fallback(self, char: str, weight: int = NORMAL_WEIGHT, italic: bool = False) -> FontMatch | None:
        """A face from the fallback families that has a glyph for ``char`` (cached per character)."""
        key = (char, weight, italic)
        cache = self._fallbacks
        if key not in cache:
            cache[key] = None
            for family in FALLBACK_FAMILIES:
                found = self.match_family(family, weight, italic)
                if found is not None and found.font.has_glyph(char):
                    cache[key] = found
                    break
        return cache[key]

    def _pick(self, faces: list[FaceInfo], weight: int, italic: bool) -> FontMatch | None:
        styled = [f for f in faces if f.italic == italic] or faces
        for info in sorted(styled, key=lambda f: _weight_rank(weight, f.weight)):
            font = self.load(info)
            if font is not None:
                return FontMatch(font, synthetic_bold=weight >= 600 and info.weight < 600,
                                 synthetic_oblique=italic and not info.italic)
        return None

    def match(self, families: str | Sequence[str] | None, weight: int | str = NORMAL_WEIGHT,
              italic: bool = False) -> list[FontMatch]:
        """Matches for each name of a ``font-family`` list, then the default family."""
        weight = weight_value(weight)
        out: list[FontMatch] = []
        seen: set[int] = set()
        for name in parse_family_list(families) + [DEFAULT_FAMILY]:
            found = self.match_family(name, weight, italic)
            if found is not None and id(found.font) not in seen:
                seen.add(id(found.font))
                out.append(found)
        return out


_default: FontDatabase | None = None
_default_lock = threading.Lock()


def default_database() -> FontDatabase:
    """The process-wide database of system fonts (scanned on first use)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = FontDatabase(system=True)
        return _default


def add_font_path(path: str | os.PathLike) -> None:
    """Make the fonts in a file or folder available to every render."""
    default_database().add_path(path)
