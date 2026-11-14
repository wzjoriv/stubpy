"""The AST pre-pass: collect structural metadata without executing the module."""
from __future__ import annotations

import ast

from ._calls import scan_forwarding
from ._directives import extract_all_extension, extract_all_list, has_ignore_directive
from ._hints import HintNames, hint_names, split_hints
from ._literals import infer_type_from_literal
from ._nodes import (
    decorator_name,
    is_implicit_alias,
    is_main_guard,
    is_stub_body,
    typevar_call_kind,
    unparse,
)
from ._params import build_raw_params, collect_annotations, infer_default_types, infer_return_type
from .models import ASTSymbols, ClassInfo, FunctionInfo, ImportInfo, TypeVarInfo, VariableInfo

_OVERLOAD_NAMES: frozenset[str] = frozenset({"overload"})


class ASTHarvester(ast.NodeVisitor):
    """Collect top-level classes, functions, variables and type declarations from source.

    Bodies of top-level ``if`` / ``try`` / ``with`` statements are visited
    too, so ``if TYPE_CHECKING:`` blocks are harvested.
    """

    def __init__(self, source: str, tree: ast.Module | None = None) -> None:
        self._source = source
        self._tree = tree
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
        self.result.classes.append(self._harvest_class(node))

    def _harvest_class(self, node: ast.ClassDef) -> ClassInfo:
        """Build a :class:`ClassInfo` from the methods, attributes and classes in the class body."""
        bases = [unparse(b) or "" for b in node.bases]
        bases += [f"{kw.arg}={unparse(kw.value)}" for kw in node.keywords if kw.arg]
        decorator_nodes, hints = split_hints(node.decorator_list, self._hint_names)
        info = ClassInfo(
            name=node.name,
            lineno=node.lineno,
            bases=[b for b in bases if b],
            decorators=[d for d in (unparse(d) for d in decorator_nodes) if d],
            hint_ignore=hints.ignore,
        )
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info.methods.append(self._harvest_function(child))
            elif isinstance(child, ast.ClassDef):
                info.classes.append(self._harvest_class(child))
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                info.attributes.append(VariableInfo(
                    name=child.target.id,
                    lineno=child.lineno,
                    annotation_str=unparse(child.annotation),
                    value_repr=unparse(child.value) if child.value else None,
                ))
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        info.attributes.append(VariableInfo(
                            name=target.id,
                            lineno=child.lineno,
                            value_repr=unparse(child.value),
                            inferred_type_str=infer_type_from_literal(child.value),
                        ))
        return info

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
        self.result.functions.append(self._harvest_function(node))

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Harvest a top-level async function."""
        self.result.functions.append(self._harvest_function(node, is_async=True))

    def visit_Assign(self, node: ast.Assign) -> None:
        """Harvest ``__all__``, TypeVar-style calls, implicit aliases and plain variables."""
        all_names = extract_all_list(node)
        if all_names is not None:
            self.result.all_exports = all_names
            return

        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id

            kind = typevar_call_kind(node.value)
            if kind:
                self.result.typevar_decls.append(TypeVarInfo(
                    name=target_name,
                    lineno=node.lineno,
                    kind=kind,
                    source_str=unparse(node.value) or "",
                ))
                return

            if is_implicit_alias(node.value):
                self.result.typevar_decls.append(TypeVarInfo(
                    name=target_name,
                    lineno=node.lineno,
                    kind="TypeAlias",
                    source_str=unparse(node.value) or "",
                ))
                return

        for target in node.targets:
            if isinstance(target, ast.Name):
                inferred = infer_type_from_literal(node.value) if node.value else None
                self.result.variables.append(VariableInfo(
                    name=target.id,
                    lineno=node.lineno,
                    annotation_str=None,
                    value_repr=unparse(node.value),
                    inferred_type_str=inferred,
                ))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Extend ``__all__`` with ``__all__ += [...]``."""
        extra = extract_all_extension(node)
        if extra is not None and self.result.all_exports is not None:
            self.result.all_exports = self.result.all_exports + extra

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
        ))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Harvest ``Name: TypeAlias = ...`` as an alias and other annotated assignments as variables."""
        if not isinstance(node.target, ast.Name):
            return
        name = node.target.id
        ann_str = unparse(node.annotation)

        if ann_str in ("TypeAlias", "typing.TypeAlias"):
            rhs = unparse(node.value) if node.value else ""
            self.result.typevar_decls.append(TypeVarInfo(
                name=name,
                lineno=node.lineno,
                kind="TypeAlias",
                source_str=rhs or "",
            ))
            return

        self.result.variables.append(VariableInfo(
            name=name,
            lineno=node.lineno,
            annotation_str=ann_str,
            value_repr=unparse(node.value) if node.value else None,
        ))

    def visit_If(self, node: ast.If) -> None:
        """Visit both branches of a top-level ``if``, skipping the body of ``if __name__ == "__main__"``."""
        body = [] if is_main_guard(node.test) else node.body
        for child in body + node.orelse:
            self.visit(child)

    def visit_Try(self, node: ast.Try) -> None:
        """Visit every block of a top-level ``try``."""
        for child in node.body + node.orelse + node.finalbody:  # type: ignore[attr-defined]
            self.visit(child)
        for handler in node.handlers:
            for child in handler.body:
                self.visit(child)

    def visit_TryStar(self, node: ast.AST) -> None:
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Visit the body of a top-level ``with``."""
        for child in node.body:
            self.visit(child)

    def generic_visit(self, node: ast.AST) -> None:  # type: ignore[override]
        pass

    def _harvest_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool | None = None,
    ) -> FunctionInfo:
        """Build a :class:`FunctionInfo`, including its variadic forwarding targets."""
        if is_async is None:
            is_async = isinstance(node, ast.AsyncFunctionDef)

        decorator_nodes, hints = split_hints(node.decorator_list, self._hint_names)
        decorators = [d for d in (unparse(d) for d in decorator_nodes) if d]
        decorator_names = [decorator_name(d) for d in decorator_nodes]
        annotations = collect_annotations(node)
        inferred = infer_default_types(node, annotations)
        forwarding = scan_forwarding(node)

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            is_async=is_async,
            decorators=decorators,
            is_overload=any(n in _OVERLOAD_NAMES for n in decorator_names),
            raw_arg_annotations=annotations,
            raw_return_annotation=unparse(node.returns),
            kwargs_forwarded_to=forwarding.kw_targets,
            args_forwarded_to=forwarding.pos_targets,
            kwargs_positional_skips=forwarding.kw_positional_skips,
            kwargs_explicit_names={k: frozenset(v) for k, v in forwarding.kw_explicit_names.items()},
            kwargs_method_targets=forwarding.kw_method_targets,
            args_method_targets=forwarding.args_method_targets,
            kwargs_unknown_starred=forwarding.kw_unknown_starred,
            kwargs_consumed=forwarding.kw_consumed,
            kwargs_injected=forwarding.kw_injected,
            kwargs_dynamic=forwarding.kw_dynamic,
            is_stub_body=is_stub_body(node.body),
            raw_arg_inferred_types=inferred,
            raw_inferred_return=infer_return_type(node),
            raw_params=build_raw_params(node, annotations, inferred),
            hint_signature=hints.signature,
            hint_returns=hints.returns,
            hint_ignore=hints.ignore,
        )


def harvest_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionInfo:
    """Return the :class:`FunctionInfo` of one function definition node."""
    return ASTHarvester("")._harvest_function(node)


def ast_harvest(source: str, tree: ast.Module | None = None) -> ASTSymbols:
    """Parse *source* and return its structural metadata without executing it.

    Parameters
    ----------
    source : str
        Python source text.
    tree : ast.Module, optional
        The already parsed *source*, to avoid parsing it twice.

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
    return ASTHarvester(source, tree).harvest()
