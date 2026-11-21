"""A template AST whose own ``List`` node shadows ``typing.List``, as Jinja's ``nodes`` module does."""
from __future__ import annotations

import typing as t


class Node:
    """Base of every template node."""


class List(Node):
    """A list literal in a template."""


class Template(Node):
    """A parsed template."""

    def __init__(self, body: t.List[Node]) -> None:
        self.body = body

    def children(self) -> t.List[Node]:
        return list(self.body)
