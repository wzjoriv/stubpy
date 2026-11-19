"""
``union_style`` applied to annotation source text: ``Optional[X]`` / ``Union[A, B]`` versus ``X | None`` / ``A | B``.
"""
from __future__ import annotations

import ast

_UNION_NAMES: frozenset[str] = frozenset({"Union", "Optional"})


def _typing_name(node: ast.expr) -> str | None:
    """Return ``Union`` / ``Optional`` for ``Union``, ``typing.Union`` or ``t.Optional``, else ``None``."""
    if isinstance(node, ast.Name) and node.id in _UNION_NAMES:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in _UNION_NAMES and isinstance(node.value, ast.Name):
        return node.attr
    return None


def _members(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _members(node.left) + _members(node.right)
    return [node]


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


class _ToModern(ast.NodeTransformer):
    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        self.generic_visit(node)
        kind = _typing_name(node.value)
        if kind is None:
            return node
        args = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        if kind == "Optional":
            args = args + [ast.Constant(None)]
        result = args[0]
        for arg in args[1:]:
            result = ast.BinOp(left=result, op=ast.BitOr(), right=arg)
        return result


class _ToLegacy(ast.NodeTransformer):
    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        if not isinstance(node.op, ast.BitOr):
            self.generic_visit(node)
            return node
        members = [self.visit(m) for m in _members(node)]
        rest = [m for m in members if not _is_none(m)]
        if len(rest) == 1 and len(members) == 2:
            return ast.Subscript(value=ast.Name("Optional"), slice=rest[0])
        return ast.Subscript(value=ast.Name("Union"), slice=ast.Tuple(elts=members))


class _Unquote(ast.NodeTransformer):
    """Replace quoted forward references by the expression they hold; ``Literal`` / ``Annotated`` arguments stay."""

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        head = node.value.attr if isinstance(node.value, ast.Attribute) else getattr(node.value, "id", "")
        if head == "Literal":
            return node
        if head == "Annotated" and isinstance(node.slice, ast.Tuple) and node.slice.elts:
            node.slice.elts[0] = self.visit(node.slice.elts[0])
            return node
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.expr:
        if not isinstance(node.value, str):
            return node
        try:
            return ast.parse(node.value.strip(), mode="eval").body
        except SyntaxError:
            return node


def restyle(text: str, modern: bool) -> str:
    """Rewrite the unions in annotation *text* to the modern (``|``) or legacy (``Union``) spelling.

    Quoted forward references are unquoted too (a stub never needs them).
    Text that does not parse is returned unchanged.

    Examples
    --------
    >>> restyle("Optional[Union[int, str]]", modern=True)
    'int | str | None'
    >>> restyle("int | None", modern=False)
    'Optional[int]'
    >>> restyle("Union['Element', str]", modern=True)
    'Element | str'
    """
    if not text or not any(c in text for c in ("Union", "Optional", "|", "'", '"')):
        return text
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return text
    before = ast.dump(tree)
    tree = _Unquote().visit(tree)
    new = ast.fix_missing_locations((_ToModern() if modern else _ToLegacy()).visit(tree))
    return text if ast.dump(new) == before else ast.unparse(new)


def style_text(text: str | None, ctx: object) -> str:
    """Apply the run's ``union_style`` to annotation source *text*; ``""`` for ``None``."""
    if not text:
        return ""
    config = getattr(ctx, "config", None)
    return restyle(text, getattr(config, "union_style", "modern") == "modern")
