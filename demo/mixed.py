# demo/mixed.py
# Mixed module: classes + functions + variables + __all__
# Exercises __all__ filtering (P2-C) with all symbol kinds
from __future__ import annotations

from typing import Optional

__all__ = ["Widget", "make_widget", "DEFAULT_COLOR"]

# Variable
DEFAULT_COLOR: str = "black"
INTERNAL_CONSTANT: int = 42  # not in __all__ → excluded

# Function
def make_widget(name: str, color: str = "black") -> "Widget":
    return Widget(name, color)

# Should be excluded — not in __all__
def _private_factory(name: str) -> "Widget":
    return Widget(name)

def helper_func(x: int) -> int:  # not in __all__ → excluded
    return x

# Class
class Widget:
    name: str
    color: str

    def __init__(self, name: str, color: str = "black") -> None:
        self.name = name
        self.color = color

    def render(self) -> str:
        return f"<{self.name}>"


class InternalWidget(Widget):  # not in __all__ → excluded
    pass
