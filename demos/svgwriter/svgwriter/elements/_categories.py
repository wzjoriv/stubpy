"""Element categories and content models."""

from __future__ import annotations

import enum

__all__ = ["Category", "ContentModel"]


class ContentModel(enum.Flag):
    """What an element may contain."""

    EMPTY = 0
    TEXT = enum.auto()
    ELEMENTS = enum.auto()
    MIXED = TEXT | ELEMENTS


class Category(enum.Enum):
    """SVG 1.1 element categories (section 1.6)."""

    ANIMATION = enum.auto()
    CONTAINER = enum.auto()
    DESCRIPTIVE = enum.auto()
    FILTER_PRIMITIVE = enum.auto()
    FONT = enum.auto()
    GRADIENT = enum.auto()
    GRAPHICS = enum.auto()
    LIGHT_SOURCE = enum.auto()
    SHAPE = enum.auto()
    STRUCTURAL = enum.auto()
    TEXT_CONTENT = enum.auto()
    PAINT_SERVER = enum.auto()
    OTHER = enum.auto()
    GROUPING = CONTAINER
