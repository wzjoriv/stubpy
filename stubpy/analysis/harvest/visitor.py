"""The AST pre-pass: collect structural metadata without executing the module."""
from __future__ import annotations

import ast

from stubpy.analysis.astutil import is_version_test, taken_branches, taken_index, version_chain

from ._classes import harvest_class
from ._directives import extract_all, extract_all_extension, has_ignore_directive
from ._functions import harvest_function, harvest_function_node
from ._hints import HintNames, hint_names
from ._literals import infer_type_from_literal
from ._nodes import (
    catches_import_error,
    findable,
    is_implicit_alias,
    is_main_guard,
    type_params,
    typevar_call_kind,
    unparse,
)
from .models import ASTSymbols, FunctionInfo, ImportInfo, TypeVarInfo, VariableInfo, VersionBlock

__all__ = ["ASTHarvester", "ast_harvest", "harvest_function"]

_TYPE_ALIAS_ANNOTATIONS: frozenset[str] = frozenset({
    "TypeAlias", "typing.TypeAlias", "typing_extensions.TypeAlias",
})


class ASTHarvester(ast.NodeVisitor):
    """Collect top-level classes, functions, variables and type declarations from source.

    Bodies of top-level ``if`` / ``try`` / ``with`` statements are visited
    too, so ``if TYPE_CHECKING:`` blocks are harvested; an ``if`` whose test
    a type checker evaluates statically (``TYPE_CHECKING``,
    ``sys.version_info``, ``sys.platform``) only contributes its taken branch.
    With *version_branches*, every branch of a ``sys.version_info`` /
    ``sys.platform`` test is harvested instead, each definition tagged with
    its ``branch``.
    """

    def __init__(self, source: str, tree: ast.Module | None = None, version_branches: bool = False) -> None:
        self._source = source
        self._tree = tree
        self._branches = version_branches
        self._hint_names = HintNames()
        self.result = ASTSymbols()

    def harvest(self) -> ASTSymbols:
        """Parse the source (unless a tree was given) and return the populated :class:`ASTSymbols`.

        Returns an empty result on :exc:`SyntaxError`, and sets
        ``skip_file`` when an ignore directive is present.
        """
        if has_ignore_directive(self._source):
            self.result.skip_file = True
            return self.result

        tree = self._tree
        if tree is None:
            try:
                tree = ast.parse(self._source)
            except SyntaxError:
                return self.result
        self._hint_names = hint_names(tree)
        for child in ast.iter_child_nodes(tree):
            self.visit(child)
        return self.result

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Harvest a top-level class."""
        self.result.classes.append(harvest_class(node, self._hint_names, self._branches))

    def visit_Import(self, node: ast.Import) -> None:
        """Record ``import a.b [as c]``."""
        for alias in node.names:
            self.result.imports.append(ImportInfo(None, alias.name, alias.asname, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record ``from .mod import name [as alias]``, keeping the relative dots."""
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self.result.imports.append(ImportInfo(module, alias.name, alias.asname, node.lineno))

    def visit_Delete(self, node: ast.Delete) -> None:
        """Forget names removed by a top-level ``del``."""
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not names:
            return
        r = self.result
        r.classes = [c for c in r.classes if c.name not in names]
        r.functions = [f for f in r.functions if f.name not in names]
        r.variables = [v for v in r.variables if v.name not in names]
        r.typevar_decls = [t for t in r.typevar_decls if t.name not in names]
        r.imports = [i for i in r.imports if i.local not in names]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Harvest a top-level function."""
        self.result.functions.append(self._function(node))

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Harvest a top-level async function."""
        self.result.functions.append(self._function(node))

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool | None = None) -> FunctionInfo:
        return harvest_function_node(node, self._hint_names, is_async)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Harvest ``__all__``, TypeVar-style calls, implicit aliases and plain variables."""
        all_items = extract_all(node)
        if all_items is not None:
            self.result.all_exports, self.result.all_spliced = all_items
            return

        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            kind = typevar_call_kind(node.value)
            if kind or is_implicit_alias(node.value) or self._is_class_alias(node.value):
                self.result.typevar_decls.append(TypeVarInfo(
                    name=target_name,
                    lineno=node.lineno,
                    kind=kind or "TypeAlias",
                    source_str=unparse(node.value) or "",
                ))
                return

        for target in node.targets:
            if isinstance(target, ast.Name):
                self.result.variables.append(VariableInfo(
                    name=target.id,
                    lineno=node.lineno,
                    annotation_str=None,
                    value_repr=unparse(node.value),
                    inferred_type_str=infer_type_from_literal(node.value) if node.value else None,
                ))

    def _is_class_alias(self, value: ast.expr | None) -> bool:
        """``True`` for ``Alias = Name`` where ``Name`` is a CamelCase class defined or imported in the module."""
        if not isinstance(value, ast.Name) or not value.id[:1].isupper() or (len(value.id) > 1 and value.id.isupper()):
            return False
        return value.id in {c.name for c in self.result.classes} | {i.local for i in self.result.imports}

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Extend ``__all__`` with ``__all__ += [...]``."""
        extra = extract_all_extension(node)
        if extra is not None and self.result.all_exports is not None:
            self.result.all_exports = self.result.all_exports + extra[0]
            self.result.all_spliced = self.result.all_spliced + extra[1]

    def visit_TypeAlias(self, node: ast.AST) -> None:
        """Harvest a Python 3.12+ ``type Name = ...`` statement."""
        name_node = getattr(node, "name", None)
        value_node = getattr(node, "value", None)
        if name_node is None or not hasattr(name_node, "id"):
            return
        self.result.typevar_decls.append(TypeVarInfo(
            name=name_node.id,
            lineno=getattr(node, "lineno", 0),
            kind="TypeAlias",
            source_str=unparse(value_node) or "",
            type_params=type_params(node),
        ))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Harvest ``Name: TypeAlias = ...`` as an alias and other annotated assignments as variables."""
        if not isinstance(node.target, ast.Name):
            return
        name = node.target.id
        ann_str = unparse(node.annotation)

        if ann_str in _TYPE_ALIAS_ANNOTATIONS:
            self.result.typevar_decls.append(TypeVarInfo(
                name=name,
                lineno=node.lineno,
                kind="TypeAlias",
                source_str=(unparse(node.value) if node.value else "") or "",
            ))
            return

        self.result.variables.append(VariableInfo(
            name=name,
            lineno=node.lineno,
            annotation_str=ann_str,
            value_repr=unparse(node.value) if node.value else None,
        ))

    def visit_If(self, node: ast.If) -> None:
        """Visit the branch(es) a type checker considers, skipping the body of ``if __name__ == "__main__"``."""
        if is_main_guard(node.test):
            children = node.orelse
        elif self._branches and is_version_test(node.test):
            self._version_block(node)
            return
        else:
            children = taken_branches(node)
        for child in children:
            self.visit(child)

    def _version_block(self, node: ast.If) -> None:
        """Visit every branch of a version ``if``, tagging what each defines with its branch."""
        chain = version_chain(node)
        block = VersionBlock(node.lineno, [unparse(t) for t, _ in chain], taken_index([t for t, _ in chain]))
        for index, (_, body) in enumerate(chain):
            r = self.result
            lists = (r.classes, r.functions, r.variables, r.typevar_decls, r.imports)
            before = [len(items) for items in lists]
            for child in body:
                self.visit(child)
            r = self.result
            for items, start in zip((r.classes, r.functions, r.variables, r.typevar_decls, r.imports), before,
                                    strict=True):
                for item in items[start:]:
                    item.branch = ((block, index), *item.branch)

    def visit_Try(self, node: ast.Try) -> None:
        """Visit every block of a top-level ``try``.

        In the optional-import pattern (``try: from x import y`` /
        ``except ImportError: <fallback y>``) the fallback definitions of the
        imported names are dropped when ``x`` is installed: the stub keeps
        the import.  When ``x`` cannot be found the fallback is what runs,
        so it stays.
        """
        for child in node.body + node.orelse + node.finalbody:  # type: ignore[attr-defined]
            self.visit(child)
        imported = {
            (a.asname or a.name).split(".")[0]
            for stmt in node.body if isinstance(stmt, (ast.Import, ast.ImportFrom)) and findable(stmt)
            for a in stmt.names
        }
        for handler in node.handlers:
            fallback = imported if catches_import_error(handler) else set()
            before = self._counts()
            for child in handler.body:
                self.visit(child)
            if fallback:
                self._drop_since(before, fallback)

    def _counts(self) -> tuple[int, int, int, int]:
        r = self.result
        return len(r.classes), len(r.functions), len(r.variables), len(r.typevar_decls)

    def _drop_since(self, before: tuple[int, int, int, int], names: set[str]) -> None:
        """Remove the definitions of *names* added after the *before* counts."""
        r = self.result
        for attr, start in zip(("classes", "functions", "variables", "typevar_decls"), before, strict=True):
            items = getattr(r, attr)
            setattr(r, attr, items[:start] + [i for i in items[start:] if i.name not in names])

    visit_TryStar = visit_Try

    def visit_With(self, node: ast.With) -> None:
        """Visit the body of a top-level ``with``."""
        for child in node.body:
            self.visit(child)

    def generic_visit(self, node: ast.AST) -> None:  # type: ignore[override]
        pass


def ast_harvest(source: str, tree: ast.Module | None = None, version_branches: bool = False) -> ASTSymbols:
    """Parse *source* and return its structural metadata without executing it.

    Parameters
    ----------
    source : str
        Python source text.
    tree : ast.Module, optional
        The already parsed *source*, to avoid parsing it twice.
    version_branches : bool
        Harvest every branch of ``sys.version_info`` / ``sys.platform``
        tests, tagging definitions with their ``branch``; by default only
        the branch this interpreter takes.

    Returns
    -------
    ASTSymbols
        Harvested classes, functions, variables, type declarations and
        ``__all__``.  Empty but valid on :exc:`SyntaxError`.

    Examples
    --------
    >>> syms = ast_harvest("class Foo(Bar): pass")
    >>> syms.classes[0].name, syms.classes[0].bases
    ('Foo', ['Bar'])
    >>> ast_harvest("X = TypeVar('X')").typevar_decls[0].kind
    'TypeVar'
    """
    return ASTHarvester(source, tree, version_branches).harvest()
