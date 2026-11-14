"""The AST pre-pass: collect structural metadata without executing the module."""
from __future__ import annotations

import ast

from ._calls import scan_forwarding
from ._directives import extract_all_list, has_ignore_directive
from ._literals import infer_type_from_literal
from ._nodes import decorator_name, is_implicit_alias, typevar_call_kind, unparse
from ._params import build_raw_params, collect_annotations, infer_default_types, infer_return_type
from .models import ASTSymbols, ClassInfo, FunctionInfo, TypeVarInfo, VariableInfo

_OVERLOAD_NAMES: frozenset[str] = frozenset({"overload"})


class ASTHarvester(ast.NodeVisitor):
    """Collect top-level classes, functions, variables and type declarations from source.

    Bodies of top-level ``if`` / ``try`` / ``with`` statements are visited
    too, so ``if TYPE_CHECKING:`` blocks are harvested.
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self.result = ASTSymbols()

    def harvest(self) -> ASTSymbols:
        """Parse the source and return the populated :class:`ASTSymbols`.

        Returns an empty result on :exc:`SyntaxError`, and sets
        ``skip_file`` when an ignore directive is present.
        """
        if has_ignore_directive(self._source):
            self.result.skip_file = True
            return self.result

        try:
            tree = ast.parse(self._source)
        except SyntaxError:
            return self.result
        for child in ast.iter_child_nodes(tree):
            self.visit(child)
        return self.result

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Harvest a class and the methods defined directly in its body."""
        bases = [unparse(b) or "" for b in node.bases]
        decorators = [decorator_name(d) for d in node.decorator_list]

        info = ClassInfo(
            name=node.name,
            lineno=node.lineno,
            bases=[b for b in bases if b],
            decorators=[d for d in decorators if d],
        )
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info.methods.append(self._harvest_function(child))

        self.result.classes.append(info)

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
        """Visit both branches of a top-level ``if``."""
        for child in node.body + node.orelse:
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

        decorator_names = [decorator_name(d) for d in node.decorator_list if decorator_name(d)]
        annotations = collect_annotations(node)
        inferred = infer_default_types(node, annotations)
        forwarding = scan_forwarding(node)

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            is_async=is_async,
            decorators=decorator_names,
            is_overload=any(n in _OVERLOAD_NAMES for n in decorator_names),
            raw_arg_annotations=annotations,
            raw_return_annotation=unparse(node.returns),
            kwargs_forwarded_to=forwarding.kw_targets,
            args_forwarded_to=forwarding.pos_targets,
            kwargs_positional_skips=forwarding.kw_positional_skips,
            kwargs_explicit_names={k: frozenset(v) for k, v in forwarding.kw_explicit_names.items()},
            kwargs_method_targets=forwarding.kw_method_targets,
            args_method_targets=forwarding.args_method_targets,
            raw_arg_inferred_types=inferred,
            raw_inferred_return=infer_return_type(node),
            raw_params=build_raw_params(node, annotations, inferred),
        )


def ast_harvest(source: str) -> ASTSymbols:
    """Parse *source* and return its structural metadata without executing it.

    Parameters
    ----------
    source : str
        Python source text.

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
    return ASTHarvester(source).harvest()
