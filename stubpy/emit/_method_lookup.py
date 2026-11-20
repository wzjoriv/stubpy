"""
Which methods a class defines, and the harvested AST info that belongs to each.
"""
from __future__ import annotations

import functools

from stubpy._constants import PUBLIC_DUNDERS
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.state.context import StubContext


def methods_defined_on(cls: type) -> list[str]:
    """Return the names of callables defined directly on a class that belong in a stub.

    Dunders outside the public set and nested classes are skipped;
    definition order is kept.

    Parameters
    ----------
    cls : type
        The class.

    Returns
    -------
    list of str
        The member names, in definition order.

    See Also
    --------
    generate_method_stub : Emits the stub for one name.

    Examples
    --------
    >>> class Parent:
    ...     def parent_method(self) -> None: ...
    >>> class Child(Parent):
    ...     def child_method(self) -> None: ...
    >>> methods_defined_on(Child)
    ['child_method']
    """
    names: list[str] = []
    for name, obj in cls.__dict__.items():
        if name.startswith("__") and name.endswith("__") and name not in PUBLIC_DUNDERS:
            continue
        if isinstance(obj, type):
            continue
        if callable(obj) or isinstance(obj, (classmethod, staticmethod, property, functools.cached_property)):
            names.append(name)
    return names


def function_ast_infos(ctx: StubContext) -> dict[str, FunctionInfo]:
    """Map each module-level function name in the symbol table to its AST info.

    The mapping is cached per table.

    Parameters
    ----------
    ctx : StubContext
        The current run context.

    Returns
    -------
    dict of str to FunctionInfo
        The infos by name; empty without a symbol table.

    Examples
    --------
    >>> function_ast_infos(StubContext())
    {}
    """
    if ctx.symbol_table is None:
        return {}
    return ctx.symbol_table.function_infos()


def _method_ast_info(
    cls: type, method_name: str, ctx: StubContext, class_info: ClassInfo | None = None,
) -> FunctionInfo | None:
    """Return the AST info of *method_name* on *cls*, from *class_info* or the symbol table."""
    if class_info is None and ctx.symbol_table is not None:
        cls_sym = ctx.symbol_table.get_class(cls.__name__)
        class_info = cls_sym.ast_info if cls_sym is not None else None
    if class_info is None:
        return None
    found = [m for m in class_info.methods if m.name == method_name and not m.is_overload]
    return found[-1] if found else None


def _class_info(cls: type, ctx: StubContext) -> ClassInfo | None:
    """Return the AST info of *cls* from the symbol table."""
    sym = ctx.symbol_table.get_class(cls.__name__) if ctx.symbol_table is not None else None
    return sym.ast_info if sym is not None else None
